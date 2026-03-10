from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from xreporter.models import ActivityRecord, TimeRange, TweetRecord, UserRecord
from xreporter.normalizer import NormalizedBatch


class SQLiteStorage:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "SQLiteStorage":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        self.close()

    @staticmethod
    def _utc_now_str() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _to_iso(dt: datetime | None) -> str | None:
        if dt is None:
            return None
        return dt.astimezone(timezone.utc).isoformat()

    def _column_exists(self, table: str, column: str) -> bool:
        rows = self._conn.execute(f"PRAGMA table_info({table})").fetchall()
        return any(str(row["name"]) == column for row in rows)

    def init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                name TEXT,
                raw_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tweets (
                id TEXT PRIMARY KEY,
                author_id TEXT,
                text TEXT,
                created_at TEXT,
                url TEXT,
                like_count INTEGER DEFAULT 0,
                retweet_count INTEGER DEFAULT 0,
                reply_count INTEGER DEFAULT 0,
                quote_count INTEGER DEFAULT 0,
                raw_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tweet_links (
                tweet_id TEXT NOT NULL,
                url TEXT NOT NULL,
                PRIMARY KEY (tweet_id, url),
                FOREIGN KEY (tweet_id) REFERENCES tweets(id)
            );

            CREATE TABLE IF NOT EXISTS activities (
                id TEXT PRIMARY KEY,
                actor_id TEXT NOT NULL,
                activity_type TEXT NOT NULL,
                event_tweet_id TEXT NOT NULL,
                event_created_at TEXT,
                event_text TEXT,
                event_url TEXT NOT NULL,
                original_tweet_id TEXT,
                original_author_id TEXT,
                original_text TEXT,
                original_url TEXT,
                like_count INTEGER DEFAULT 0,
                retweet_count INTEGER DEFAULT 0,
                reply_count INTEGER DEFAULT 0,
                quote_count INTEGER DEFAULT 0,
                raw_event_json TEXT NOT NULL,
                raw_original_json TEXT,
                raw_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (actor_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                target_user_id TEXT NOT NULL,
                since_utc TEXT NOT NULL,
                until_utc TEXT NOT NULL,
                api_provider TEXT NOT NULL DEFAULT 'official',
                include_replies INTEGER NOT NULL,
                following_cap INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL,
                error_message TEXT,
                total_followings INTEGER NOT NULL DEFAULT 0,
                total_activities INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS run_activities (
                run_id INTEGER NOT NULL,
                activity_id TEXT NOT NULL,
                PRIMARY KEY (run_id, activity_id),
                FOREIGN KEY (run_id) REFERENCES runs(id),
                FOREIGN KEY (activity_id) REFERENCES activities(id)
            );

            CREATE INDEX IF NOT EXISTS idx_activities_event_created_at ON activities(event_created_at);
            CREATE INDEX IF NOT EXISTS idx_run_activities_run_id ON run_activities(run_id);
            """
        )
        if not self._column_exists("runs", "api_provider"):
            self._conn.execute(
                """
                ALTER TABLE runs
                ADD COLUMN api_provider TEXT NOT NULL DEFAULT 'official'
                """
            )
        self._conn.commit()

    def create_run(
        self,
        *,
        username: str,
        target_user_id: str,
        api_provider: str,
        time_range: TimeRange,
        include_replies: bool,
        following_cap: int,
    ) -> int:
        cursor = self._conn.execute(
            """
            INSERT INTO runs (
                username,
                target_user_id,
                since_utc,
                until_utc,
                api_provider,
                include_replies,
                following_cap,
                started_at,
                status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                username,
                target_user_id,
                self._to_iso(time_range.since),
                self._to_iso(time_range.until),
                api_provider,
                1 if include_replies else 0,
                following_cap,
                self._utc_now_str(),
                "running",
            ),
        )
        self._conn.commit()
        return int(cursor.lastrowid)

    def finish_run(
        self,
        *,
        run_id: int,
        status: str,
        total_followings: int,
        total_activities: int,
        error_message: str | None = None,
    ) -> None:
        self._conn.execute(
            """
            UPDATE runs
            SET status = ?,
                total_followings = ?,
                total_activities = ?,
                error_message = ?,
                finished_at = ?
            WHERE id = ?
            """,
            (
                status,
                total_followings,
                total_activities,
                error_message,
                self._utc_now_str(),
                run_id,
            ),
        )
        self._conn.commit()

    def upsert_user(self, user: UserRecord) -> None:
        self._conn.execute(
            """
            INSERT INTO users (id, username, name, raw_json, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                username = excluded.username,
                name = excluded.name,
                raw_json = excluded.raw_json,
                updated_at = excluded.updated_at
            """,
            (
                user.id,
                user.username,
                user.name,
                json.dumps(user.raw_json, ensure_ascii=False),
                self._utc_now_str(),
            ),
        )

    def upsert_tweet(self, tweet: TweetRecord) -> None:
        self._conn.execute(
            """
            INSERT INTO tweets (
                id,
                author_id,
                text,
                created_at,
                url,
                like_count,
                retweet_count,
                reply_count,
                quote_count,
                raw_json,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                author_id = excluded.author_id,
                text = excluded.text,
                created_at = excluded.created_at,
                url = excluded.url,
                like_count = excluded.like_count,
                retweet_count = excluded.retweet_count,
                reply_count = excluded.reply_count,
                quote_count = excluded.quote_count,
                raw_json = excluded.raw_json,
                updated_at = excluded.updated_at
            """,
            (
                tweet.id,
                tweet.author_id,
                tweet.text,
                self._to_iso(tweet.created_at),
                tweet.url,
                tweet.like_count,
                tweet.retweet_count,
                tweet.reply_count,
                tweet.quote_count,
                json.dumps(tweet.raw_json, ensure_ascii=False),
                self._utc_now_str(),
            ),
        )
        for link in tweet.links:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO tweet_links (tweet_id, url)
                VALUES (?, ?)
                """,
                (tweet.id, link),
            )

    def upsert_activity(self, activity: ActivityRecord) -> None:
        raw_json: dict[str, Any] = {
            "id": activity.id,
            "actor_id": activity.actor_id,
            "activity_type": activity.activity_type.value,
            "event_tweet_id": activity.event_tweet_id,
            "original_tweet_id": activity.original_tweet_id,
        }

        self._conn.execute(
            """
            INSERT INTO activities (
                id,
                actor_id,
                activity_type,
                event_tweet_id,
                event_created_at,
                event_text,
                event_url,
                original_tweet_id,
                original_author_id,
                original_text,
                original_url,
                like_count,
                retweet_count,
                reply_count,
                quote_count,
                raw_event_json,
                raw_original_json,
                raw_json,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                actor_id = excluded.actor_id,
                activity_type = excluded.activity_type,
                event_tweet_id = excluded.event_tweet_id,
                event_created_at = excluded.event_created_at,
                event_text = excluded.event_text,
                event_url = excluded.event_url,
                original_tweet_id = excluded.original_tweet_id,
                original_author_id = excluded.original_author_id,
                original_text = excluded.original_text,
                original_url = excluded.original_url,
                like_count = excluded.like_count,
                retweet_count = excluded.retweet_count,
                reply_count = excluded.reply_count,
                quote_count = excluded.quote_count,
                raw_event_json = excluded.raw_event_json,
                raw_original_json = excluded.raw_original_json,
                raw_json = excluded.raw_json,
                updated_at = excluded.updated_at
            """,
            (
                activity.id,
                activity.actor_id,
                activity.activity_type.value,
                activity.event_tweet_id,
                self._to_iso(activity.event_created_at),
                activity.event_text,
                activity.event_url,
                activity.original_tweet_id,
                activity.original_author_id,
                activity.original_text,
                activity.original_url,
                activity.like_count,
                activity.retweet_count,
                activity.reply_count,
                activity.quote_count,
                json.dumps(activity.raw_event_json, ensure_ascii=False),
                json.dumps(activity.raw_original_json, ensure_ascii=False)
                if activity.raw_original_json is not None
                else None,
                json.dumps(raw_json, ensure_ascii=False),
                self._utc_now_str(),
                self._utc_now_str(),
            ),
        )

    def add_run_activity(self, run_id: int, activity_id: str) -> None:
        self._conn.execute(
            """
            INSERT OR IGNORE INTO run_activities (run_id, activity_id)
            VALUES (?, ?)
            """,
            (run_id, activity_id),
        )

    def persist_batch(self, run_id: int, batch: NormalizedBatch) -> None:
        with self._conn:
            for user in batch.users.values():
                self.upsert_user(user)
            for tweet in batch.tweets.values():
                self.upsert_tweet(tweet)
            for activity in batch.activities:
                self.upsert_activity(activity)
                self.add_run_activity(run_id, activity.id)

    def get_latest_run_id(self) -> int | None:
        row = self._conn.execute("SELECT id FROM runs ORDER BY id DESC LIMIT 1").fetchone()
        if not row:
            return None
        return int(row["id"])

    def get_run(self, run_id: int) -> dict[str, Any] | None:
        row = self._conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            return None
        return dict(row)

    def get_activities_for_run(self, run_id: int) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT
                a.*,
                actor.username AS actor_username,
                actor.name AS actor_name,
                orig_user.username AS original_author_username,
                orig_user.name AS original_author_name
            FROM run_activities ra
            JOIN activities a ON a.id = ra.activity_id
            LEFT JOIN users actor ON actor.id = a.actor_id
            LEFT JOIN users orig_user ON orig_user.id = a.original_author_id
            WHERE ra.run_id = ?
            ORDER BY a.event_created_at DESC, a.id DESC
            """,
            (run_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def count_rows(self, table: str) -> int:
        if table not in {
            "users",
            "tweets",
            "tweet_links",
            "activities",
            "runs",
            "run_activities",
        }:
            raise ValueError("Unsupported table name")
        row = self._conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()
        return int(row["c"])
