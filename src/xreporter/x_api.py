from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import httpx

from xreporter.models import TimeRange


DEFAULT_BASE_URL = "https://api.x.com/2"
USER_FIELDS = "id,name,username,verified,public_metrics,profile_image_url"
TWEET_FIELDS = (
    "id,text,author_id,created_at,conversation_id,referenced_tweets,"
    "public_metrics,entities,in_reply_to_user_id"
)
EXPANSIONS = "author_id,referenced_tweets.id,referenced_tweets.id.author_id"


class XApiError(RuntimeError):
    """Raised for X API errors."""


class ApiClientProtocol(Protocol):
    def get_user_by_username(self, username: str) -> dict[str, Any]:
        ...

    def get_followings(self, user_id: str, limit: int) -> list[dict[str, Any]]:
        ...

    def get_user_timeline(
        self,
        user: dict[str, Any],
        time_range: TimeRange,
        include_replies: bool,
    ) -> "TimelinePayload":
        ...


@dataclass
class TimelinePayload:
    tweets: list[dict[str, Any]]
    include_users: dict[str, dict[str, Any]]
    include_tweets: dict[str, dict[str, Any]]


class XApiClient:
    def __init__(
        self,
        token: str,
        *,
        client: httpx.Client | None = None,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
        max_retries: int = 5,
        sleep_func=time.sleep,
        random_func=random.random,
    ) -> None:
        if not token:
            raise ValueError("X_BEARER_TOKEN is required")

        self._max_retries = max_retries
        self._sleep = sleep_func
        self._random = random_func
        self._client = client or httpx.Client(
            base_url=base_url,
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": "XReporter/0.1",
            },
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "XApiClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        self.close()

    def _request_json(self, method: str, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        attempts = 0
        while True:
            try:
                response = self._client.request(method, path, params=params)
            except httpx.HTTPError as exc:
                if attempts >= self._max_retries:
                    raise XApiError(f"Network error after retries: {exc}") from exc
                delay = min(2**attempts, 30) + self._random()
                self._sleep(delay)
                attempts += 1
                continue

            if response.status_code < 400:
                return response.json()

            retriable = response.status_code == 429 or response.status_code >= 500
            if not retriable or attempts >= self._max_retries:
                raise XApiError(
                    f"X API request failed ({response.status_code}) path={path} body={response.text[:300]}"
                )

            retry_after = response.headers.get("retry-after")
            if retry_after and retry_after.isdigit():
                delay = float(retry_after)
            else:
                delay = min(2**attempts, 30) + self._random()

            self._sleep(delay)
            attempts += 1

    @staticmethod
    def _as_utc_iso(dt: datetime) -> str:
        return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    def get_user_by_username(self, username: str) -> dict[str, Any]:
        payload = self._request_json(
            "GET",
            f"/users/by/username/{username}",
            params={"user.fields": USER_FIELDS},
        )
        data = payload.get("data")
        if not data:
            raise XApiError(f"User not found: {username}")
        return data

    def get_followings(self, user_id: str, limit: int) -> list[dict[str, Any]]:
        if limit <= 0:
            return []

        followings: list[dict[str, Any]] = []
        pagination_token: str | None = None

        while len(followings) < limit:
            remaining = limit - len(followings)
            max_results = min(1000, max(10, remaining))
            params: dict[str, Any] = {
                "max_results": max_results,
                "user.fields": USER_FIELDS,
            }
            if pagination_token:
                params["pagination_token"] = pagination_token

            payload = self._request_json("GET", f"/users/{user_id}/following", params=params)
            data = payload.get("data", [])
            if not data:
                break
            followings.extend(data)

            pagination_token = payload.get("meta", {}).get("next_token")
            if not pagination_token:
                break

        return followings[:limit]

    def get_tweets_by_ids(self, tweet_ids: list[str]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
        tweet_map: dict[str, dict[str, Any]] = {}
        user_map: dict[str, dict[str, Any]] = {}
        if not tweet_ids:
            return tweet_map, user_map

        for i in range(0, len(tweet_ids), 100):
            chunk = tweet_ids[i : i + 100]
            payload = self._request_json(
                "GET",
                "/tweets",
                params={
                    "ids": ",".join(chunk),
                    "tweet.fields": TWEET_FIELDS,
                    "expansions": "author_id",
                    "user.fields": USER_FIELDS,
                },
            )
            for item in payload.get("data", []):
                tweet_map[item["id"]] = item
            for item in payload.get("includes", {}).get("users", []):
                user_map[item["id"]] = item

        return tweet_map, user_map

    def get_user_timeline(
        self,
        user: dict[str, Any],
        time_range: TimeRange,
        include_replies: bool,
    ) -> TimelinePayload:
        user_id = user["id"]

        tweets: dict[str, dict[str, Any]] = {}
        include_users: dict[str, dict[str, Any]] = {user_id: user}
        include_tweets: dict[str, dict[str, Any]] = {}

        pagination_token: str | None = None
        while True:
            params: dict[str, Any] = {
                "max_results": 100,
                "start_time": self._as_utc_iso(time_range.since),
                "end_time": self._as_utc_iso(time_range.until),
                "tweet.fields": TWEET_FIELDS,
                "expansions": EXPANSIONS,
                "user.fields": USER_FIELDS,
            }
            if not include_replies:
                params["exclude"] = "replies"
            if pagination_token:
                params["pagination_token"] = pagination_token

            payload = self._request_json("GET", f"/users/{user_id}/tweets", params=params)

            for item in payload.get("data", []):
                tweets[item["id"]] = item

            includes = payload.get("includes", {})
            for item in includes.get("users", []):
                include_users[item["id"]] = item
            for item in includes.get("tweets", []):
                include_tweets[item["id"]] = item

            pagination_token = payload.get("meta", {}).get("next_token")
            if not pagination_token:
                break

        unresolved_ids: list[str] = []
        for item in tweets.values():
            for ref in item.get("referenced_tweets", []):
                ref_id = ref.get("id")
                if not ref_id:
                    continue
                if ref_id in include_tweets or ref_id in tweets:
                    continue
                unresolved_ids.append(ref_id)

        unresolved_ids = sorted(set(unresolved_ids))
        if unresolved_ids:
            fetched_tweets, fetched_users = self.get_tweets_by_ids(unresolved_ids)
            include_tweets.update(fetched_tweets)
            include_users.update(fetched_users)

        return TimelinePayload(
            tweets=list(tweets.values()),
            include_users=include_users,
            include_tweets=include_tweets,
        )


class FixtureXApiClient:
    """Fixture-backed API client for tests and offline demos."""

    def __init__(self, fixture_path: Path) -> None:
        self.fixture_path = fixture_path
        self._data = json.loads(fixture_path.read_text(encoding="utf-8"))

    def close(self) -> None:
        return None

    def __enter__(self) -> "FixtureXApiClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        self.close()

    def get_user_by_username(self, username: str) -> dict[str, Any]:
        user = self._data.get("users_by_username", {}).get(username)
        if not user:
            raise XApiError(f"Fixture user not found: {username}")
        return dict(user)

    def get_followings(self, user_id: str, limit: int) -> list[dict[str, Any]]:
        followings = self._data.get("followings_by_user_id", {}).get(user_id, [])
        return [dict(item) for item in followings[:limit]]

    def get_tweets_by_ids(self, tweet_ids: list[str]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
        tweet_map: dict[str, dict[str, Any]] = {}
        users: dict[str, dict[str, Any]] = {}
        all_tweets = self._data.get("tweets_by_id", {})
        all_users = self._data.get("users_by_id", {})
        for tid in tweet_ids:
            if tid in all_tweets:
                tweet = dict(all_tweets[tid])
                tweet_map[tid] = tweet
                author_id = tweet.get("author_id")
                if author_id and author_id in all_users:
                    users[author_id] = dict(all_users[author_id])
        return tweet_map, users

    def get_user_timeline(
        self,
        user: dict[str, Any],
        time_range: TimeRange,
        include_replies: bool,
    ) -> TimelinePayload:
        user_id = user["id"]
        payload = self._data.get("timelines_by_user_id", {}).get(user_id, {})
        data = payload.get("data", [])
        includes = payload.get("includes", {})

        include_users = {item["id"]: dict(item) for item in includes.get("users", [])}
        include_users[user_id] = dict(user)
        include_tweets = {item["id"]: dict(item) for item in includes.get("tweets", [])}

        selected: list[dict[str, Any]] = []
        for item in data:
            created_at = _parse_created_at(item.get("created_at"))
            if created_at:
                if created_at < time_range.since or created_at > time_range.until:
                    continue
            if not include_replies:
                refs = item.get("referenced_tweets", [])
                if any(ref.get("type") == "replied_to" for ref in refs):
                    continue
            selected.append(dict(item))

        unresolved: list[str] = []
        for item in selected:
            for ref in item.get("referenced_tweets", []):
                ref_id = ref.get("id")
                if not ref_id:
                    continue
                if ref_id in include_tweets:
                    continue
                unresolved.append(ref_id)

        unresolved = sorted(set(unresolved))
        if unresolved:
            fetched_tweets, fetched_users = self.get_tweets_by_ids(unresolved)
            include_tweets.update(fetched_tweets)
            include_users.update(fetched_users)

        return TimelinePayload(
            tweets=selected,
            include_users=include_users,
            include_tweets=include_tweets,
        )


def _parse_created_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None
