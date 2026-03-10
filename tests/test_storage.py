import sqlite3
from datetime import datetime, timezone

from xreporter.models import ActivityRecord, ActivityType, TimeRange, TweetRecord, UserRecord
from xreporter.normalizer import NormalizedBatch
from xreporter.storage import SQLiteStorage


def _make_batch() -> NormalizedBatch:
    user = UserRecord(id="1", username="alice", name="Alice", raw_json={"id": "1", "username": "alice"})
    tweet = TweetRecord(
        id="t1",
        author_id="1",
        text="hello",
        created_at=datetime(2026, 3, 10, 1, 0, tzinfo=timezone.utc),
        url="https://x.com/alice/status/t1",
        like_count=1,
        retweet_count=0,
        reply_count=0,
        quote_count=0,
        links=["https://example.com"],
        raw_json={"id": "t1"},
    )
    activity = ActivityRecord(
        id="t1",
        actor_id="1",
        activity_type=ActivityType.TWEET,
        event_tweet_id="t1",
        event_created_at=datetime(2026, 3, 10, 1, 0, tzinfo=timezone.utc),
        event_text="hello",
        event_url="https://x.com/alice/status/t1",
        original_tweet_id=None,
        original_author_id=None,
        original_text=None,
        original_url=None,
        like_count=1,
        retweet_count=0,
        reply_count=0,
        quote_count=0,
        raw_event_json={"id": "t1"},
        raw_original_json=None,
    )
    return NormalizedBatch(users={"1": user}, tweets={"t1": tweet}, activities=[activity])


def test_upsert_and_run_activity_idempotency(tmp_path) -> None:
    db_path = tmp_path / "xreporter.db"
    storage = SQLiteStorage(db_path)
    storage.init_schema()

    time_range = TimeRange(
        since=datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc),
        until=datetime(2026, 3, 10, 2, 0, tzinfo=timezone.utc),
    )
    run_1 = storage.create_run(
        username="target",
        target_user_id="100",
        api_provider="official",
        time_range=time_range,
        include_replies=True,
        following_cap=10,
    )
    storage.persist_batch(run_1, _make_batch())
    storage.finish_run(run_id=run_1, status="success", total_followings=1, total_activities=1)

    run_2 = storage.create_run(
        username="target",
        target_user_id="100",
        api_provider="official",
        time_range=time_range,
        include_replies=True,
        following_cap=10,
    )
    storage.persist_batch(run_2, _make_batch())
    storage.finish_run(run_id=run_2, status="success", total_followings=1, total_activities=1)

    assert storage.count_rows("users") == 1
    assert storage.count_rows("tweets") == 1
    assert storage.count_rows("activities") == 1
    assert storage.count_rows("run_activities") == 2

    storage.close()


def test_runs_table_migrates_api_provider_column(tmp_path) -> None:
    db_path = tmp_path / "xreporter.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            target_user_id TEXT NOT NULL,
            since_utc TEXT NOT NULL,
            until_utc TEXT NOT NULL,
            include_replies INTEGER NOT NULL,
            following_cap INTEGER NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL,
            error_message TEXT,
            total_followings INTEGER NOT NULL DEFAULT 0,
            total_activities INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    conn.commit()
    conn.close()

    storage = SQLiteStorage(db_path)
    storage.init_schema()

    columns = storage._conn.execute("PRAGMA table_info(runs)").fetchall()  # noqa: SLF001
    column_names = {row["name"] for row in columns}
    assert "api_provider" in column_names

    time_range = TimeRange(
        since=datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc),
        until=datetime(2026, 3, 10, 2, 0, tzinfo=timezone.utc),
    )
    run_id = storage.create_run(
        username="target",
        target_user_id="100",
        api_provider="socialdata",
        time_range=time_range,
        include_replies=True,
        following_cap=10,
    )
    row = storage.get_run(run_id)
    assert row is not None
    assert row["api_provider"] == "socialdata"
    storage.close()
