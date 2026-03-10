from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from rich.progress import Progress

from xreporter.models import TimeRange
from xreporter.service import CollectorService
from xreporter.storage import SQLiteStorage
from xreporter.x_api import ApiRequestError, TimelinePayload


class _ApiWithPrivacy403:
    def get_user_by_username(self, username: str) -> dict[str, str]:
        return {"id": "100", "username": username, "name": "Target"}

    def get_followings(self, user_id: str, limit: int) -> list[dict[str, str]]:
        return [
            {"id": "200", "username": "locked_user", "name": "Locked User"},
            {"id": "201", "username": "open_user", "name": "Open User"},
        ][:limit]

    def get_user_timeline(
        self,
        user: dict[str, str],
        time_range: TimeRange,
        include_replies: bool,
    ) -> TimelinePayload:
        if user["id"] == "200":
            raise ApiRequestError(
                provider="socialdata",
                status_code=403,
                path="/twitter/tweets/1237555686118047749",
                body='{"status":"error","message":"Forbidden: Requested resource cannot be viewed due to user\'s privacy settings"}',
                message_prefix="SocialData request failed",
            )

        return TimelinePayload(
            tweets=[],
            include_users={user["id"]: dict(user)},
            include_tweets={},
        )


def test_service_skips_socialdata_private_403_and_records_warning(tmp_path: Path) -> None:
    storage = SQLiteStorage(tmp_path / "xreporter.db")
    storage.init_schema()

    service = CollectorService(storage=storage, api_client=_ApiWithPrivacy403())
    time_range = TimeRange(
        since=datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc),
        until=datetime(2026, 3, 10, 2, 0, tzinfo=timezone.utc),
    )

    with Progress() as progress:
        result = service.collect_with_error_handling(
            username="target",
            api_provider="socialdata",
            time_range=time_range,
            following_cap=2,
            include_replies=True,
            progress=progress,
            labels={"resolve": "resolve", "followings": "followings", "timelines": "timelines"},
        )

    assert result.total_followings == 2
    assert result.total_activities == 0
    assert result.total_warnings == 1

    run = storage.get_run(result.run_id)
    assert run is not None
    assert run["status"] == "success"
    assert run["total_followings"] == 2
    assert run["total_activities"] == 0

    warnings = storage.get_warnings_for_run(result.run_id)
    assert len(warnings) == 1
    assert warnings[0]["provider"] == "socialdata"
    assert warnings[0]["warning_type"] == "private_content_403"
    assert warnings[0]["username"] == "locked_user"
    assert warnings[0]["resource_url"] == "https://x.com/i/web/status/1237555686118047749"

    storage.close()
