from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import threading
import time

import pytest
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


class _ConcurrentApi:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.active = 0
        self.max_active = 0

    def get_user_by_username(self, username: str) -> dict[str, str]:
        return {"id": "100", "username": username, "name": "Target"}

    def get_followings(self, user_id: str, limit: int) -> list[dict[str, str]]:
        return [
            {"id": "200", "username": "u200", "name": "U200"},
            {"id": "201", "username": "u201", "name": "U201"},
            {"id": "202", "username": "u202", "name": "U202"},
            {"id": "203", "username": "u203", "name": "U203"},
        ][:limit]

    def get_user_timeline(
        self,
        user: dict[str, str],
        time_range: TimeRange,
        include_replies: bool,
    ) -> TimelinePayload:
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        time.sleep(0.05)
        with self._lock:
            self.active -= 1
        return TimelinePayload(
            tweets=[],
            include_users={user["id"]: dict(user)},
            include_tweets={},
        )


class _FailOnceApi:
    def __init__(self) -> None:
        self.failed = False

    def get_user_by_username(self, username: str) -> dict[str, str]:
        return {"id": "100", "username": username, "name": "Target"}

    def get_followings(self, user_id: str, limit: int) -> list[dict[str, str]]:
        return [
            {"id": "200", "username": "u200", "name": "U200"},
            {"id": "201", "username": "u201", "name": "U201"},
            {"id": "202", "username": "u202", "name": "U202"},
        ][:limit]

    def get_user_timeline(
        self,
        user: dict[str, str],
        time_range: TimeRange,
        include_replies: bool,
    ) -> TimelinePayload:
        if user["id"] == "201" and not self.failed:
            self.failed = True
            raise RuntimeError("transient timeline failure")
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


def test_service_collects_timelines_concurrently(tmp_path: Path) -> None:
    api = _ConcurrentApi()
    storage = SQLiteStorage(tmp_path / "xreporter.db")
    storage.init_schema()

    service = CollectorService(storage=storage, api_client=api)
    time_range = TimeRange(
        since=datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc),
        until=datetime(2026, 3, 10, 2, 0, tzinfo=timezone.utc),
    )

    with Progress() as progress:
        result = service.collect_with_error_handling(
            username="target",
            api_provider="official",
            time_range=time_range,
            following_cap=4,
            include_replies=True,
            api_concurrency=4,
            progress=progress,
            labels={"resolve": "resolve", "followings": "followings", "timelines": "timelines"},
        )

    assert result.total_followings == 4
    assert api.max_active >= 2
    assert storage.get_pending_run_followings(result.run_id) == []

    storage.close()


def test_service_resume_run_after_failure(tmp_path: Path) -> None:
    storage = SQLiteStorage(tmp_path / "xreporter.db")
    storage.init_schema()
    api = _FailOnceApi()
    service = CollectorService(storage=storage, api_client=api)
    time_range = TimeRange(
        since=datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc),
        until=datetime(2026, 3, 10, 2, 0, tzinfo=timezone.utc),
    )

    with Progress() as progress:
        with pytest.raises(RuntimeError, match="transient timeline failure"):
            service.collect_with_error_handling(
                username="target",
                api_provider="official",
                time_range=time_range,
                following_cap=3,
                include_replies=True,
                api_concurrency=1,
                progress=progress,
                labels={"resolve": "resolve", "followings": "followings", "timelines": "timelines"},
            )

    run_id = storage.get_latest_run_id()
    assert run_id is not None
    failed_run = storage.get_run(run_id)
    assert failed_run is not None
    assert failed_run["status"] == "failed"
    assert len(storage.get_pending_run_followings(run_id)) >= 1

    with Progress() as progress:
        resumed = service.collect_with_error_handling(
            username="ignored-on-resume",
            api_provider="official",
            time_range=time_range,
            following_cap=3,
            include_replies=True,
            api_concurrency=2,
            resume_run_id=run_id,
            progress=progress,
            labels={"resolve": "resolve", "followings": "followings", "timelines": "timelines"},
        )

    assert resumed.run_id == run_id
    assert resumed.total_followings == 3
    assert storage.get_pending_run_followings(run_id) == []
    resumed_run = storage.get_run(run_id)
    assert resumed_run is not None
    assert resumed_run["status"] == "success"

    storage.close()
