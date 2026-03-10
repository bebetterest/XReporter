from __future__ import annotations

from dataclasses import dataclass

from rich.progress import Progress

from xreporter.models import TimeRange
from xreporter.normalizer import normalize_timeline
from xreporter.storage import SQLiteStorage
from xreporter.x_api import ApiClientProtocol


@dataclass
class CollectResult:
    run_id: int
    total_followings: int
    total_activities: int


class CollectorService:
    def __init__(self, storage: SQLiteStorage, api_client: ApiClientProtocol) -> None:
        self.storage = storage
        self.api_client = api_client

    def collect_with_error_handling(
        self,
        *,
        username: str,
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
            time_range=time_range,
            include_replies=include_replies,
            following_cap=following_cap,
        )

        timelines_task = progress.add_task(labels["timelines"], total=max(1, len(followings)))
        total_activities = 0

        try:
            for following in followings:
                payload = self.api_client.get_user_timeline(following, time_range, include_replies)
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
        )
