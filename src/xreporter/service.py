from __future__ import annotations

from dataclasses import dataclass
import re

from rich.progress import Progress

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


@dataclass
class CollectResult:
    run_id: int
    total_followings: int
    total_activities: int
    total_warnings: int


class CollectorService:
    def __init__(self, storage: SQLiteStorage, api_client: ApiClientProtocol) -> None:
        self.storage = storage
        self.api_client = api_client

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
    ) -> CollectResult:
        resolve_task = progress.add_task(labels["resolve"], total=1)
        target_user = self.api_client.get_user_by_username(username)
        progress.advance(resolve_task)

        followings_task = progress.add_task(labels["followings"], total=1)
        followings = self.api_client.get_followings(target_user["id"], following_cap)
        progress.advance(followings_task)

        run_id = self.storage.create_run(
            username=username,
            target_user_id=target_user["id"],
            api_provider=api_provider,
            time_range=time_range,
            include_replies=include_replies,
            following_cap=following_cap,
        )

        timelines_task = progress.add_task(labels["timelines"], total=max(1, len(followings)))
        total_activities = 0
        total_warnings = 0

        try:
            for following in followings:
                try:
                    payload = self.api_client.get_user_timeline(following, time_range, include_replies)
                except ApiRequestError as exc:
                    if _is_socialdata_private_error(api_provider, exc):
                        warning = _build_socialdata_private_warning(following, exc)
                        self.storage.add_run_warning(run_id, warning)
                        total_warnings += 1
                        progress.advance(timelines_task)
                        continue
                    raise
                batch = normalize_timeline(following, payload)
                self.storage.persist_batch(run_id, batch)
                total_activities += len(batch.activities)
                progress.advance(timelines_task)
        except Exception as exc:
            self.storage.finish_run(
                run_id=run_id,
                status="failed",
                total_followings=len(followings),
                total_activities=total_activities,
                error_message=str(exc),
            )
            raise

        self.storage.finish_run(
            run_id=run_id,
            status="success",
            total_followings=len(followings),
            total_activities=total_activities,
        )

        return CollectResult(
            run_id=run_id,
            total_followings=len(followings),
            total_activities=total_activities,
            total_warnings=total_warnings,
        )
