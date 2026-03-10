from __future__ import annotations

import asyncio
import inspect
import json
import os
import random
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import httpx

from xreporter.models import TimeRange


DEFAULT_BASE_URL = "https://api.x.com/2"
DEFAULT_SOCIALDATA_BASE_URL = "https://api.socialdata.tools"
USER_FIELDS = "id,name,username,verified,public_metrics,profile_image_url"
TWEET_FIELDS = (
    "id,text,author_id,created_at,conversation_id,referenced_tweets,"
    "public_metrics,entities,in_reply_to_user_id"
)
EXPANSIONS = "author_id,referenced_tweets.id,referenced_tweets.id.author_id"


class XApiError(RuntimeError):
    """Raised for API provider errors."""


class ApiRequestError(XApiError):
    """Raised for non-retriable provider HTTP errors."""

    def __init__(
        self,
        *,
        provider: str,
        status_code: int,
        path: str,
        body: str,
        message_prefix: str,
    ) -> None:
        self.provider = provider
        self.status_code = status_code
        self.path = path
        self.body = body
        super().__init__(f"{message_prefix} ({status_code}) path={path} body={body[:300]}")


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
                raise ApiRequestError(
                    provider="official",
                    status_code=response.status_code,
                    path=path,
                    body=response.text[:2000],
                    message_prefix="X API request failed",
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


class SocialDataApiClient:
    def __init__(
        self,
        token: str,
        *,
        client: httpx.Client | None = None,
        base_url: str = DEFAULT_SOCIALDATA_BASE_URL,
        timeout: float = 30.0,
        max_retries: int = 5,
        sleep_func=time.sleep,
        random_func=random.random,
    ) -> None:
        if not token:
            raise ValueError("SOCIALDATA_API_KEY is required")

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

    def __enter__(self) -> "SocialDataApiClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        self.close()

    def _request_json(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        allow_not_found: bool = False,
    ) -> dict[str, Any] | None:
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

            if response.status_code == 404 and allow_not_found:
                return None

            retriable = response.status_code == 429 or response.status_code >= 500
            if not retriable or attempts >= self._max_retries:
                raise ApiRequestError(
                    provider="socialdata",
                    status_code=response.status_code,
                    path=path,
                    body=response.text[:2000],
                    message_prefix="SocialData request failed",
                )

            retry_after = response.headers.get("retry-after")
            if retry_after and retry_after.isdigit():
                delay = float(retry_after)
            else:
                delay = min(2**attempts, 30) + self._random()

            self._sleep(delay)
            attempts += 1

    def _request_json_with_fallbacks(
        self,
        method: str,
        path_with_params: list[tuple[str, dict[str, Any] | None]],
    ) -> dict[str, Any]:
        for i, (path, params) in enumerate(path_with_params):
            payload = self._request_json(method, path, params=params, allow_not_found=i < len(path_with_params) - 1)
            if payload is not None:
                return payload
        raise XApiError("SocialData request failed: no fallback endpoint resolved")

    def get_user_by_username(self, username: str) -> dict[str, Any]:
        payload = self._request_json_with_fallbacks(
            "GET",
            [
                (f"/twitter/user/{username}", None),
                ("/twitter/user/profile", {"username": username}),
            ],
        )
        user_item = _extract_single_item(payload)
        user = _normalize_social_user(user_item)
        if not user:
            raise XApiError(f"User not found: {username}")
        return user

    def get_followings(self, user_id: str, limit: int) -> list[dict[str, Any]]:
        if limit <= 0:
            return []

        followings: list[dict[str, Any]] = []
        cursor: str | None = None

        while len(followings) < limit:
            remaining = limit - len(followings)
            params: dict[str, Any] = {"limit": min(remaining, 100)}
            if cursor:
                params["cursor"] = cursor

            payload = self._request_json_with_fallbacks(
                "GET",
                [
                    (f"/twitter/user/{user_id}/following", params),
                    (f"/twitter/user/{user_id}/followings", params),
                ],
            )
            items = _extract_items(payload)
            if not items:
                break

            for item in items:
                user = _normalize_social_user(item)
                if user:
                    followings.append(user)
                    if len(followings) >= limit:
                        break

            cursor = _extract_next_cursor(payload)
            if not cursor:
                break

        return followings[:limit]

    def get_tweets_by_ids(self, tweet_ids: list[str]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
        tweet_map: dict[str, dict[str, Any]] = {}
        user_map: dict[str, dict[str, Any]] = {}

        for tweet_id in tweet_ids:
            payload = self._request_json("GET", f"/twitter/tweet/{tweet_id}", allow_not_found=True)
            if payload is None:
                payload = self._request_json("GET", f"/twitter/tweets/{tweet_id}", allow_not_found=True)
            if payload is None:
                continue
            tweet_item = _extract_single_item(payload)
            tweet = _normalize_social_tweet(tweet_item)
            if not tweet:
                continue
            tweet_map[tweet["id"]] = tweet

            nested_user = _extract_nested_user(tweet_item)
            if nested_user:
                user_map[nested_user["id"]] = nested_user
            elif tweet.get("author_id"):
                author = _normalize_social_user(_extract_author_from_payload(payload))
                if author:
                    user_map[author["id"]] = author

            for include_user in _extract_include_users(payload):
                user_map[include_user["id"]] = include_user

        return tweet_map, user_map

    def get_user_timeline(
        self,
        user: dict[str, Any],
        time_range: TimeRange,
        include_replies: bool,
    ) -> TimelinePayload:
        user_id = str(user["id"])

        tweets: dict[str, dict[str, Any]] = {}
        include_users: dict[str, dict[str, Any]] = {user_id: dict(user)}
        include_tweets: dict[str, dict[str, Any]] = {}

        cursor: str | None = None
        while True:
            params: dict[str, Any] = {"limit": 100}
            if cursor:
                params["cursor"] = cursor

            path_candidates = [
                (
                    f"/twitter/user/{user_id}/tweets-and-replies"
                    if include_replies
                    else f"/twitter/user/{user_id}/tweets",
                    params,
                )
            ]
            if include_replies:
                path_candidates.append((f"/twitter/user/{user_id}/tweets", params))

            payload = self._request_json_with_fallbacks("GET", path_candidates)

            for item in _extract_items(payload):
                tweet = _normalize_social_tweet(item)
                if not tweet:
                    continue

                created_at = _parse_created_at(tweet.get("created_at"))
                if created_at and (created_at < time_range.since or created_at > time_range.until):
                    continue
                if not include_replies and _is_reply(tweet):
                    continue

                tweets[tweet["id"]] = tweet

                nested_user = _extract_nested_user(item)
                if nested_user:
                    include_users[nested_user["id"]] = nested_user

            for include_user in _extract_include_users(payload):
                include_users[include_user["id"]] = include_user
            for include_tweet in _extract_include_tweets(payload):
                include_tweets[include_tweet["id"]] = include_tweet

            cursor = _extract_next_cursor(payload)
            if not cursor:
                break

        unresolved_ids: list[str] = []
        for item in tweets.values():
            for ref in item.get("referenced_tweets", []):
                ref_id = str(ref.get("id", ""))
                if not ref_id:
                    continue
                if ref_id in tweets or ref_id in include_tweets:
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


class TwscrapeApiClient:
    def __init__(
        self,
        accounts_db_path: Path,
        *,
        username: str | None = None,
        password: str | None = None,
        email: str | None = None,
        email_password: str | None = None,
        api: Any | None = None,
        auto_login: bool = True,
    ) -> None:
        self.accounts_db_path = accounts_db_path
        self.accounts_db_path.parent.mkdir(parents=True, exist_ok=True)

        self._username = username or os.getenv("XREPORTER_TWS_USERNAME", "")
        self._password = password or os.getenv("XREPORTER_TWS_PASSWORD", "")
        self._email = email or os.getenv("XREPORTER_TWS_EMAIL", "")
        self._email_password = email_password or os.getenv("XREPORTER_TWS_EMAIL_PASSWORD", "")

        self._owns_api = api is None
        if api is not None:
            self._api = api
        else:
            try:
                from twscrape import API, AccountsPool  # type: ignore[import-not-found]
            except ImportError as exc:
                raise XApiError("twscrape is not installed. Install dependencies and retry.") from exc

            pool = AccountsPool(str(self.accounts_db_path))
            self._api = API(pool=pool)

        if auto_login:
            self._run_async(self._ensure_login())

    def close(self) -> None:
        close_func = getattr(self._api, "close", None)
        if not callable(close_func):
            return
        result = close_func()
        if inspect.isawaitable(result):
            self._run_async(result)

    def __enter__(self) -> "TwscrapeApiClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        self.close()

    def _missing_credentials(self) -> list[str]:
        required = {
            "XREPORTER_TWS_USERNAME": self._username,
            "XREPORTER_TWS_PASSWORD": self._password,
            "XREPORTER_TWS_EMAIL": self._email,
            "XREPORTER_TWS_EMAIL_PASSWORD": self._email_password,
        }
        return [name for name, value in required.items() if not value]

    def _run_async(self, coro: Any) -> Any:
        if not inspect.isawaitable(coro):
            return coro
        try:
            return asyncio.run(coro)
        except RuntimeError as exc:
            if "asyncio.run() cannot be called from a running event loop" not in str(exc):
                raise
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

    async def _ensure_login(self) -> None:
        pool = getattr(self._api, "pool", None)
        if pool is None:
            raise XApiError("twscrape API pool is unavailable")

        has_existing_accounts = twscrape_accounts_db_has_account(self.accounts_db_path)
        missing = self._missing_credentials()
        has_full_credentials = not missing
        if not has_existing_accounts and not has_full_credentials:
            raise ValueError("Missing twscrape credentials: " + ", ".join(missing))

        add_account = getattr(pool, "add_account", None)
        if callable(add_account) and has_full_credentials:
            try:
                await add_account(
                    self._username,
                    self._password,
                    self._email,
                    self._email_password,
                )
            except Exception as exc:  # noqa: BLE001
                if "already" not in str(exc).lower():
                    raise XApiError(f"Failed to add twscrape account: {exc}") from exc

        login_all = getattr(pool, "login_all", None)
        if callable(login_all):
            await login_all()

    async def _resolve_user_by_username(self, username: str) -> dict[str, Any]:
        method = getattr(self._api, "user_by_login", None) or getattr(self._api, "user_by_username", None)
        if not callable(method):
            raise XApiError("twscrape API missing user lookup method")

        user_obj = await method(username)
        user = _normalize_tws_user(user_obj)
        if not user:
            raise XApiError(f"User not found: {username}")
        return user

    async def _collect_followings(self, user_id: str, limit: int) -> list[dict[str, Any]]:
        method = getattr(self._api, "following", None)
        if not callable(method):
            raise XApiError("twscrape API missing following method")

        results: list[dict[str, Any]] = []
        stream = _call_tws_method(method, user_id, limit=limit)
        async for item in _iterate_any_stream(stream):
            user = _normalize_tws_user(item)
            if user:
                results.append(user)
            if len(results) >= limit:
                break
        return results[:limit]

    async def _tweet_by_id(self, tweet_id: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        for method_name in ("tweet_details", "tweet_by_id", "tweet"):
            method = getattr(self._api, method_name, None)
            if not callable(method):
                continue
            result = _call_tws_method(method, tweet_id)
            value = await _await_if_needed(result)
            if value is None:
                continue
            tweet, _, _ = _normalize_tws_tweet(value)
            if tweet:
                return tweet, _extract_tws_author(value)
        return None, None

    async def _collect_timeline(
        self,
        user: dict[str, Any],
        time_range: TimeRange,
        include_replies: bool,
    ) -> TimelinePayload:
        user_id = str(user["id"])
        method = (
            getattr(self._api, "user_tweets_and_replies", None)
            if include_replies
            else getattr(self._api, "user_tweets", None)
        )
        if method is None and include_replies:
            method = getattr(self._api, "user_tweets", None)
        if not callable(method):
            raise XApiError("twscrape API missing timeline method")

        tweets: dict[str, dict[str, Any]] = {}
        include_users: dict[str, dict[str, Any]] = {user_id: dict(user)}
        include_tweets: dict[str, dict[str, Any]] = {}

        stream = _call_tws_method(method, user_id)
        async for item in _iterate_any_stream(stream):
            tweet, nested_tweets, nested_users = _normalize_tws_tweet(item)
            if not tweet:
                continue

            created_at = _parse_created_at(tweet.get("created_at"))
            if created_at and created_at < time_range.since:
                # twscrape APIs emit newest-first timeline entries.
                break
            if created_at and created_at > time_range.until:
                continue
            if not include_replies and _is_reply(tweet):
                continue

            tweets[tweet["id"]] = tweet
            include_tweets.update(nested_tweets)
            include_users.update(nested_users)

            author_id = str(tweet.get("author_id", ""))
            if author_id and author_id not in include_users:
                author = _extract_tws_author(item)
                if author:
                    include_users[author["id"]] = author

        unresolved_ids: list[str] = []
        for item in tweets.values():
            for ref in item.get("referenced_tweets", []):
                ref_id = str(ref.get("id", ""))
                if not ref_id:
                    continue
                if ref_id in tweets or ref_id in include_tweets:
                    continue
                unresolved_ids.append(ref_id)

        for ref_id in sorted(set(unresolved_ids)):
            tweet, author = await self._tweet_by_id(ref_id)
            if tweet:
                include_tweets[tweet["id"]] = tweet
            if author:
                include_users[author["id"]] = author

        return TimelinePayload(
            tweets=list(tweets.values()),
            include_users=include_users,
            include_tweets=include_tweets,
        )

    def get_user_by_username(self, username: str) -> dict[str, Any]:
        return self._run_async(self._resolve_user_by_username(username))

    def get_followings(self, user_id: str, limit: int) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        return self._run_async(self._collect_followings(user_id, limit))

    def get_user_timeline(
        self,
        user: dict[str, Any],
        time_range: TimeRange,
        include_replies: bool,
    ) -> TimelinePayload:
        return self._run_async(self._collect_timeline(user, time_range, include_replies))


def twscrape_accounts_db_has_account(accounts_db_path: Path) -> bool:
    if not accounts_db_path.exists():
        return False

    try:
        with sqlite3.connect(str(accounts_db_path)) as conn:
            table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='accounts' LIMIT 1"
            ).fetchone()
            if table is None:
                return False
            row = conn.execute("SELECT 1 FROM accounts LIMIT 1").fetchone()
            return row is not None
    except sqlite3.Error:
        return False


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


def _pick(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if "." in key:
            current: Any = data
            parts = key.split(".")
            ok = True
            for part in parts:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    ok = False
                    break
            if ok and current is not None:
                return current
            continue
        if key in data and data[key] is not None:
            return data[key]
    return None


def _obj_pick(item: Any, *keys: str) -> Any:
    if isinstance(item, dict):
        return _pick(item, *keys)
    for key in keys:
        if hasattr(item, key):
            value = getattr(item, key)
            if value is not None:
                return value
    return None


def _to_iso8601(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    if isinstance(value, str):
        parsed = _parse_created_at(value)
        if parsed is None:
            return value
        return parsed.isoformat(timespec="seconds").replace("+00:00", "Z")
    return str(value)


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if not isinstance(payload, dict):
        return []

    for key in ("data", "results", "items", "users", "tweets", "followings", "following"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = _extract_items(value)
            if nested:
                return nested

    if any(field in payload for field in ("id", "user_id", "rest_id", "tweet_id")):
        return [payload]

    return []


def _extract_single_item(payload: Any) -> dict[str, Any]:
    items = _extract_items(payload)
    if items:
        return items[0]
    if isinstance(payload, dict):
        return payload
    return {}


def _extract_next_cursor(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None

    for key in ("next_cursor", "nextCursor", "cursor", "next", "next_token"):
        value = payload.get(key)
        if value:
            return str(value)

    for key in ("meta", "pagination", "data"):
        value = payload.get(key)
        if isinstance(value, dict):
            nested = _extract_next_cursor(value)
            if nested:
                return nested

    return None


def _normalize_public_metrics(metrics: Any) -> dict[str, int]:
    if not isinstance(metrics, dict):
        metrics = {}
    return {
        "like_count": int(_pick(metrics, "like_count", "likes", "favorite_count", "favoriteCount") or 0),
        "retweet_count": int(_pick(metrics, "retweet_count", "retweets", "retweetCount") or 0),
        "reply_count": int(_pick(metrics, "reply_count", "replies", "replyCount") or 0),
        "quote_count": int(_pick(metrics, "quote_count", "quotes", "quoteCount") or 0),
    }


def _extract_links(item: dict[str, Any]) -> list[dict[str, str]]:
    urls: list[str] = []
    entities = item.get("entities")
    if isinstance(entities, dict):
        for info in entities.get("urls", []):
            if not isinstance(info, dict):
                continue
            for key in ("expanded_url", "unwound_url", "url"):
                value = info.get(key)
                if value:
                    urls.append(str(value))
                    break

    for key in ("links", "outlinks", "outLinks"):
        value = item.get(key)
        if isinstance(value, list):
            for link in value:
                if isinstance(link, str):
                    urls.append(link)
                elif isinstance(link, dict):
                    link_value = _pick(link, "expanded_url", "url", "href")
                    if link_value:
                        urls.append(str(link_value))

    unique = sorted(set(urls))
    return [{"expanded_url": value} for value in unique]


def _normalize_social_user(item: dict[str, Any]) -> dict[str, Any] | None:
    user_id = _pick(item, "id", "user_id", "userId", "rest_id")
    if user_id is None:
        return None

    username = _pick(item, "username", "screen_name", "screenName", "handle")
    name = _pick(item, "name", "display_name", "displayName", "full_name")
    metrics = _normalize_public_metrics(
        _pick(item, "public_metrics")
        or {
            "followers_count": _pick(item, "followers_count", "followersCount"),
            "following_count": _pick(item, "following_count", "friends_count", "friendsCount"),
            "tweet_count": _pick(item, "statuses_count", "tweet_count", "tweetCount"),
        }
    )

    return {
        "id": str(user_id),
        "username": str(username or ""),
        "name": str(name or username or user_id),
        "verified": bool(_pick(item, "verified", "is_verified", "isVerified") or False),
        "public_metrics": metrics,
        "raw_json": item,
    }


def _extract_social_references(item: dict[str, Any]) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []

    if isinstance(item.get("referenced_tweets"), list):
        for ref in item["referenced_tweets"]:
            if not isinstance(ref, dict):
                continue
            ref_id = ref.get("id")
            ref_type = ref.get("type")
            if ref_id and ref_type:
                refs.append({"id": str(ref_id), "type": str(ref_type)})

    if not refs:
        lookup: list[tuple[str, str]] = [
            ("retweeted_status_id", "retweeted"),
            ("retweetedTweetId", "retweeted"),
            ("quoted_status_id", "quoted"),
            ("quotedTweetId", "quoted"),
            ("in_reply_to_status_id", "replied_to"),
            ("inReplyToTweetId", "replied_to"),
        ]
        for key, ref_type in lookup:
            ref_id = _pick(item, key)
            if ref_id:
                refs.append({"id": str(ref_id), "type": ref_type})

    dedup: dict[tuple[str, str], dict[str, str]] = {}
    for ref in refs:
        dedup[(ref["id"], ref["type"])] = ref
    return list(dedup.values())


def _normalize_social_tweet(item: dict[str, Any]) -> dict[str, Any] | None:
    tweet_id = _pick(item, "id", "tweet_id", "tweetId", "rest_id")
    if tweet_id is None:
        return None

    author_id = _pick(item, "author_id", "authorId", "user_id", "userId", "user.id")
    text = _pick(item, "text", "full_text", "fullText", "rawContent", "content")
    created_at = _to_iso8601(_pick(item, "created_at", "createdAt", "date"))

    metrics = _normalize_public_metrics(
        _pick(item, "public_metrics", "stats")
        or {
            "favorite_count": _pick(item, "favorite_count", "favoriteCount"),
            "retweet_count": _pick(item, "retweet_count", "retweetCount"),
            "reply_count": _pick(item, "reply_count", "replyCount"),
            "quote_count": _pick(item, "quote_count", "quoteCount"),
        }
    )

    tweet: dict[str, Any] = {
        "id": str(tweet_id),
        "author_id": str(author_id) if author_id is not None else None,
        "text": str(text or ""),
        "created_at": created_at,
        "referenced_tweets": _extract_social_references(item),
        "public_metrics": metrics,
        "entities": {"urls": _extract_links(item)},
    }

    return tweet


def _extract_nested_user(item: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("user", "author", "author_info", "authorInfo"):
        value = item.get(key)
        if isinstance(value, dict):
            user = _normalize_social_user(value)
            if user:
                return user
    return None


def _extract_author_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    for key in ("user", "author", "profile"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    if isinstance(payload.get("data"), dict):
        return _extract_author_from_payload(payload["data"])
    return {}


def _extract_include_users(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []

    includes = payload.get("includes")
    candidates: list[Any] = []
    if isinstance(includes, dict):
        candidates.extend(includes.get("users", []))

    data = payload.get("data")
    if isinstance(data, dict):
        if isinstance(data.get("includes"), dict):
            candidates.extend(data["includes"].get("users", []))
        if isinstance(data.get("users"), list):
            candidates.extend(data.get("users", []))

    normalized: list[dict[str, Any]] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        user = _normalize_social_user(item)
        if user:
            normalized.append(user)
    return normalized


def _extract_include_tweets(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []

    includes = payload.get("includes")
    candidates: list[Any] = []
    if isinstance(includes, dict):
        candidates.extend(includes.get("tweets", []))

    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("includes"), dict):
        candidates.extend(data["includes"].get("tweets", []))

    normalized: list[dict[str, Any]] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        tweet = _normalize_social_tweet(item)
        if tweet:
            normalized.append(tweet)
    return normalized


def _normalize_tws_user(item: Any) -> dict[str, Any] | None:
    user_id = _obj_pick(item, "id", "userId", "user_id", "rest_id")
    if user_id is None:
        return None

    username = _obj_pick(item, "username", "userName", "screenname", "screen_name", "handle")
    name = _obj_pick(item, "displayname", "displayName", "name", "fullName")

    metrics_source = _obj_pick(item, "public_metrics", "stats")
    metrics: dict[str, int]
    if isinstance(metrics_source, dict):
        metrics = _normalize_public_metrics(metrics_source)
    else:
        metrics = {
            "like_count": 0,
            "retweet_count": 0,
            "reply_count": 0,
            "quote_count": 0,
        }

    raw = _to_plain_dict(item)

    return {
        "id": str(user_id),
        "username": str(username or ""),
        "name": str(name or username or user_id),
        "verified": bool(_obj_pick(item, "verified", "isBlueVerified", "isVerified") or False),
        "public_metrics": metrics,
        "raw_json": raw,
    }


def _extract_tws_author(item: Any) -> dict[str, Any] | None:
    author_obj = _obj_pick(item, "user", "author")
    if author_obj is None:
        return None
    return _normalize_tws_user(author_obj)


def _normalize_tws_tweet(item: Any) -> tuple[dict[str, Any] | None, dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    tweet = _normalize_tws_simple_tweet(item)
    if not tweet:
        return None, {}, {}

    include_tweets: dict[str, dict[str, Any]] = {}
    include_users: dict[str, dict[str, Any]] = {}

    refs = list(tweet.get("referenced_tweets", []))

    nested_pairs = [
        ("retweetedTweet", "retweeted"),
        ("retweeted_tweet", "retweeted"),
        ("quotedTweet", "quoted"),
        ("quoted_tweet", "quoted"),
        ("repliedTweet", "replied_to"),
        ("replied_tweet", "replied_to"),
    ]
    for field, ref_type in nested_pairs:
        nested = _obj_pick(item, field)
        nested_tweet = _normalize_tws_simple_tweet(nested)
        if not nested_tweet:
            continue
        include_tweets[nested_tweet["id"]] = nested_tweet
        refs.append({"id": nested_tweet["id"], "type": ref_type})

        nested_author = _extract_tws_author(nested)
        if nested_author:
            include_users[nested_author["id"]] = nested_author

    reply_id = _obj_pick(item, "inReplyToTweetId", "in_reply_to_tweet_id", "in_reply_to_status_id")
    if reply_id:
        refs.append({"id": str(reply_id), "type": "replied_to"})

    quote_id = _obj_pick(item, "quotedTweetId", "quoted_status_id")
    if quote_id:
        refs.append({"id": str(quote_id), "type": "quoted"})

    retweet_id = _obj_pick(item, "retweetedTweetId", "retweeted_status_id")
    if retweet_id:
        refs.append({"id": str(retweet_id), "type": "retweeted"})

    dedup: dict[tuple[str, str], dict[str, str]] = {}
    for ref in refs:
        ref_id = str(ref.get("id", ""))
        ref_type = str(ref.get("type", ""))
        if ref_id and ref_type:
            dedup[(ref_id, ref_type)] = {"id": ref_id, "type": ref_type}

    tweet["referenced_tweets"] = list(dedup.values())
    return tweet, include_tweets, include_users


def _normalize_tws_simple_tweet(item: Any) -> dict[str, Any] | None:
    if item is None:
        return None

    tweet_id = _obj_pick(item, "id", "tweetId", "tweet_id", "rest_id")
    if tweet_id is None:
        return None

    author_id = _obj_pick(item, "userId", "user_id", "authorId", "author_id", "user.id")
    text = _obj_pick(item, "rawContent", "full_text", "fullText", "text", "content")
    created_at = _to_iso8601(_obj_pick(item, "date", "created_at", "createdAt"))

    stats = _obj_pick(item, "stats", "public_metrics")
    if isinstance(stats, dict):
        metrics = _normalize_public_metrics(stats)
    else:
        metrics = _normalize_public_metrics(
            {
                "likes": _obj_pick(item, "like_count", "favorite_count"),
                "retweets": _obj_pick(item, "retweet_count"),
                "replies": _obj_pick(item, "reply_count"),
                "quotes": _obj_pick(item, "quote_count"),
            }
        )

    raw = _to_plain_dict(item)
    urls = _extract_links(raw)

    return {
        "id": str(tweet_id),
        "author_id": str(author_id) if author_id is not None else None,
        "text": str(text or ""),
        "created_at": created_at,
        "referenced_tweets": [],
        "public_metrics": metrics,
        "entities": {"urls": urls},
    }


def _to_plain_dict(item: Any) -> dict[str, Any]:
    if isinstance(item, dict):
        return dict(item)

    model_dump = getattr(item, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, dict):
            return dumped

    dict_method = getattr(item, "dict", None)
    if callable(dict_method):
        dumped = dict_method()
        if isinstance(dumped, dict):
            return dumped

    asdict_method = getattr(item, "asdict", None)
    if callable(asdict_method):
        dumped = asdict_method()
        if isinstance(dumped, dict):
            return dumped

    if hasattr(item, "__dict__"):
        result: dict[str, Any] = {}
        for key, value in vars(item).items():
            if key.startswith("_"):
                continue
            result[key] = value
        return result

    return {}


def _call_tws_method(method: Any, primary_id: str, *, limit: int | None = None) -> Any:
    candidates: list[Any] = [primary_id]
    if primary_id.isdigit():
        candidates.insert(0, int(primary_id))

    last_exc: Exception | None = None
    for value in candidates:
        try:
            if limit is None:
                return method(value)
            return method(value, limit=limit)
        except TypeError:
            try:
                return method(value)
            except TypeError as exc:
                last_exc = exc
                continue

    if last_exc:
        raise XApiError(f"Unsupported twscrape method signature: {last_exc}") from last_exc
    raise XApiError("Unsupported twscrape method signature")


async def _await_if_needed(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def _iterate_any_stream(value: Any):
    target = await _await_if_needed(value)

    if hasattr(target, "__aiter__"):
        async for item in target:
            yield item
        return

    if isinstance(target, list):
        for item in target:
            yield item
        return

    if target is not None:
        yield target


def _is_reply(tweet: dict[str, Any]) -> bool:
    refs = tweet.get("referenced_tweets", [])
    return any(ref.get("type") == "replied_to" for ref in refs if isinstance(ref, dict))


def _parse_created_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None
