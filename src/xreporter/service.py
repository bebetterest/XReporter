from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any

from rich.progress import Progress

from xreporter.logging_utils import get_logger
from xreporter.models import RunWarning, TimeRange
from xreporter.normalizer import normalize_timeline
from xreporter.storage import SQLiteStorage
from xreporter.x_api import ApiClientProtocol, ApiRequestError


_SOCIALDATA_TWEET_PATH_RE = re.compile(r"^/twitter/tweets?/([^/?]+)$")


def _is_socialdata_private_error(api_provider: str, exc: ApiRequestError) -> bool:
    if api_provider != "socialdata":
        return False
    if exc.provider != "socialdata" or exc.status_code != 403:
        return False

    body = exc.body.lower()
    return "privacy settings" in body or "private" in body


def _guess_x_resource_url(path: str, following: dict[str, object]) -> str | None:
    match = _SOCIALDATA_TWEET_PATH_RE.match(path)
    if match:
        tweet_id = match.group(1).strip()
        if tweet_id:
            return f"https://x.com/i/web/status/{tweet_id}"

    username = str(following.get("username", "") or "").strip()
    if username:
        return f"https://x.com/{username}"
    return None


def _build_socialdata_private_warning(following: dict[str, object], exc: ApiRequestError) -> RunWarning:
    user_id = str(following.get("id", "") or "").strip() or None
    username = str(following.get("username", "") or "").strip() or None
    return RunWarning(
        provider="socialdata",
        warning_type="private_content_403",
        status_code=exc.status_code,
        user_id=user_id,
        username=username,
        resource_url=_guess_x_resource_url(exc.path, following),
        api_path=exc.path,
        message="Skipped private content due to SocialData privacy restriction.",
        raw_error=exc.body,
    )


def _parse_run_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass
class CollectResult:
    run_id: int
    total_followings: int
    total_activities: int
    total_warnings: int


@dataclass
class _TimelineJob:
    position: int
    following: dict[str, Any]


class CollectorService:
    def __init__(self, storage: SQLiteStorage, api_client: ApiClientProtocol) -> None:
        self.storage = storage
        self.api_client = api_client
        self.logger = get_logger("service.collector")

    def collect_with_error_handling(
        self,
        *,
        username: str,
        api_provider: str,
        time_range: TimeRange,
        following_cap: int,
        include_replies: bool,
        progress: Progress,
        labels: dict[str, str],
        api_concurrency: int = 4,
        resume_run_id: int | None = None,
    ) -> CollectResult:
        if api_concurrency <= 0:
            raise ValueError("api_concurrency must be > 0")

        self.logger.info(
            "collector start username=%s provider=%s since=%s until=%s following_cap=%d include_replies=%s "
            "api_concurrency=%d resume_run_id=%s",
            username,
            api_provider,
            time_range.since.isoformat(),
            time_range.until.isoformat(),
            following_cap,
            include_replies,
            api_concurrency,
            resume_run_id,
        )

        resolve_task = progress.add_task(labels["resolve"], total=1)
        followings_task = progress.add_task(labels["followings"], total=1)

        run_id: int
        total_followings: int

        if resume_run_id is not None:
            run = self.storage.get_run(resume_run_id)
            if not run:
                raise ValueError(f"Run not found for resume: {resume_run_id}")

            run_provider = str(run.get("api_provider", "") or "").strip()
            if run_provider != api_provider:
                raise ValueError(
                    f"Resume run provider mismatch: run={run_provider}, current={api_provider}"
                )

            run_id = resume_run_id
            username = str(run.get("username", "") or username)
            target_user_id = str(run.get("target_user_id", "") or "").strip()
            if not target_user_id:
                raise ValueError(f"Run {run_id} is missing target_user_id")

            since_raw = str(run.get("since_utc", "") or "").strip()
            until_raw = str(run.get("until_utc", "") or "").strip()
            if not since_raw or not until_raw:
                raise ValueError(f"Run {run_id} is missing time range for resume")
            time_range = TimeRange(since=_parse_run_time(since_raw), until=_parse_run_time(until_raw))
            include_replies = bool(int(run.get("include_replies", 1)))
            following_cap = int(run.get("following_cap", following_cap))

            progress.advance(resolve_task)

            followings = self.storage.get_run_followings(run_id)
            if followings:
                total_followings = len(followings)
                self.logger.info(
                    "collector resume using persisted followings run_id=%d total=%d",
                    run_id,
                    total_followings,
                )
            else:
                followings = self.api_client.get_followings(target_user_id, following_cap)
                total_followings = self.storage.init_run_followings(run_id, followings)
                self.logger.info(
                    "collector resume refetched followings run_id=%d target_user_id=%s total=%d",
                    run_id,
                    target_user_id,
                    total_followings,
                )
            progress.advance(followings_task)
            self.storage.mark_run_running(run_id)
        else:
            target_user = self.api_client.get_user_by_username(username)
            self.logger.info(
                "collector resolved target username=%s target_user_id=%s",
                username,
                target_user.get("id"),
            )
            progress.advance(resolve_task)

            followings = self.api_client.get_followings(target_user["id"], following_cap)
            self.logger.info(
                "collector fetched followings target_user_id=%s total=%d",
                target_user.get("id"),
                len(followings),
            )
            progress.advance(followings_task)

            run_id = self.storage.create_run(
                username=username,
                target_user_id=target_user["id"],
                api_provider=api_provider,
                time_range=time_range,
                include_replies=include_replies,
                following_cap=following_cap,
            )
            total_followings = self.storage.init_run_followings(run_id, followings)
            self.logger.info("collector run created run_id=%d", run_id)

        pending_followings = self.storage.get_pending_run_followings(run_id)
        completed_followings = max(0, total_followings - len(pending_followings))
        timelines_task = progress.add_task(
            labels["timelines"],
            total=max(1, total_followings),
            completed=completed_followings,
        )
        total_activities = self.storage.count_run_activities(run_id)
        total_warnings = self.storage.count_run_warnings(run_id)

        try:
            if pending_followings:
                worker_count = min(api_concurrency, len(pending_followings))
                self.logger.info(
                    "collector timeline dispatch run_id=%d worker_count=%d pending=%d total=%d",
                    run_id,
                    worker_count,
                    len(pending_followings),
                    total_followings,
                )

                futures: dict[Future[Any], _TimelineJob] = {}
                with ThreadPoolExecutor(max_workers=worker_count) as executor:
                    for following in pending_followings:
                        following_user_id = str(following.get("id", "") or "").strip()
                        if not following_user_id:
                            progress.advance(timelines_task)
                            continue
                        position = int(following.get("ordinal", 0) or 0)
                        following_username = str(following.get("username", "") or "")
                        self.storage.mark_run_following_in_progress(run_id, following_user_id)
                        self.logger.debug(
                            "collector timeline start run_id=%d item=%d/%d user_id=%s username=%s",
                            run_id,
                            position,
                            total_followings,
                            following_user_id,
                            following_username,
                        )
                        actor = {
                            "id": following_user_id,
                            "username": following_username,
                            "name": following_username,
                        }
                        future = executor.submit(
                            self.api_client.get_user_timeline,
                            actor,
                            time_range,
                            include_replies,
                        )
                        futures[future] = _TimelineJob(
                            position=position,
                            following=actor,
                        )

                    for future in as_completed(futures):
                        job = futures[future]
                        following_user_id = str(job.following.get("id", ""))
                        following_username = str(job.following.get("username", ""))
                        try:
                            payload = future.result()
                        except ApiRequestError as exc:
                            if _is_socialdata_private_error(api_provider, exc):
                                warning = _build_socialdata_private_warning(job.following, exc)
                                self.storage.add_run_warning(run_id, warning)
                                self.storage.mark_run_following_warning(run_id, following_user_id, warning.message)
                                total_warnings = self.storage.count_run_warnings(run_id)
                                self.logger.warning(
                                    "collector warning run_id=%d item=%d/%d user_id=%s username=%s type=%s path=%s status_code=%s",
                                    run_id,
                                    job.position,
                                    total_followings,
                                    following_user_id,
                                    following_username,
                                    warning.warning_type,
                                    warning.api_path,
                                    warning.status_code,
                                )
                                progress.advance(timelines_task)
                                continue

                            self.storage.mark_run_following_failed(run_id, following_user_id, str(exc))
                            raise
                        except Exception as exc:
                            self.storage.mark_run_following_failed(run_id, following_user_id, str(exc))
                            raise

                        batch = normalize_timeline(job.following, payload)
                        self.storage.persist_batch(run_id, batch)
                        self.storage.mark_run_following_success(run_id, following_user_id, len(batch.activities))
                        total_activities = self.storage.count_run_activities(run_id)
                        self.logger.info(
                            "collector timeline done run_id=%d item=%d/%d user_id=%s username=%s batch_activities=%d total_activities=%d",
                            run_id,
                            job.position,
                            total_followings,
                            following_user_id,
                            following_username,
                            len(batch.activities),
                            total_activities,
                        )
                        progress.advance(timelines_task)
            else:
                self.logger.debug(
                    "collector resume has no pending followings run_id=%d total=%d",
                    run_id,
                    total_followings,
                )

            total_activities = self.storage.count_run_activities(run_id)
            total_warnings = self.storage.count_run_warnings(run_id)
        except BaseException as exc:
            status = "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
            total_activities = self.storage.count_run_activities(run_id)
            total_warnings = self.storage.count_run_warnings(run_id)
            self.logger.exception(
                "collector failed run_id=%d status=%s total_followings=%d total_activities=%d total_warnings=%d",
                run_id,
                status,
                total_followings,
                total_activities,
                total_warnings,
            )
            self.storage.finish_run(
                run_id=run_id,
                status=status,
                total_followings=total_followings,
                total_activities=total_activities,
                error_message=str(exc),
            )
            raise

        self.storage.finish_run(
            run_id=run_id,
            status="success",
            total_followings=total_followings,
            total_activities=total_activities,
        )
        self.logger.info(
            "collector success run_id=%d total_followings=%d total_activities=%d total_warnings=%d",
            run_id,
            total_followings,
            total_activities,
            total_warnings,
        )

        return CollectResult(
            run_id=run_id,
            total_followings=total_followings,
            total_activities=total_activities,
            total_warnings=total_warnings,
        )
