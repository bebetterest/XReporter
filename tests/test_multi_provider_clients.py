from __future__ import annotations

from datetime import datetime, timezone
import json

import httpx

from xreporter.models import TimeRange
from xreporter.x_api import SocialDataApiClient


def test_socialdata_retry_then_success() -> None:
    attempts = {"n": 0}
    sleeps: list[float] = []
    retry_notices: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/twitter/user/demo":
            attempts["n"] += 1
            if attempts["n"] == 1:
                return httpx.Response(429, json={"error": "rate limited"})
            return httpx.Response(
                200,
                json={"data": {"id": "10", "username": "demo", "name": "Demo"}},
            )
        raise AssertionError(f"Unexpected URL: {request.url}")

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.socialdata.tools")
    api = SocialDataApiClient(
        token="test",
        client=client,
        sleep_func=lambda delay: sleeps.append(delay),
        random_func=lambda: 0.0,
        max_retries=3,
        retry_callback=lambda message: retry_notices.append(message),
    )

    user = api.get_user_by_username("demo")
    assert user["id"] == "10"
    assert attempts["n"] == 2
    assert sleeps == [1.0]
    assert len(retry_notices) == 1
    assert "provider=socialdata" in retry_notices[0]
    assert "/twitter/user/demo" in retry_notices[0]
    api.close()


def test_socialdata_timeline_backfills_referenced_tweets() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/twitter/user/2/tweets-and-replies":
            assert "limit" not in request.url.params
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "200",
                            "author_id": "2",
                            "text": "rt",
                            "created_at": "2026-03-10T01:00:00Z",
                            "referenced_tweets": [{"type": "retweeted", "id": "999"}],
                        }
                    ]
                },
            )

        if request.method == "POST" and request.url.path == "/twitter/tweets-by-ids":
            payload = json.loads(request.content.decode("utf-8"))
            assert payload["ids"] == ["999"]
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "999",
                            "author_id": "30",
                            "text": "origin",
                            "created_at": "2026-03-10T00:30:00Z",
                            "user": {"id": "30", "username": "orig", "name": "Orig"},
                        }
                    ]
                },
            )

        raise AssertionError(f"Unexpected URL: {request.url}")

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.socialdata.tools")
    api = SocialDataApiClient(token="test", client=client)

    payload = api.get_user_timeline(
        user={"id": "2", "username": "u2", "name": "U2"},
        time_range=TimeRange(
            since=datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc),
            until=datetime(2026, 3, 10, 2, 0, tzinfo=timezone.utc),
        ),
        include_replies=True,
    )

    assert "999" in payload.include_tweets
    assert payload.include_tweets["999"]["text"] == "origin"
    assert "30" in payload.include_users
    api.close()


def test_socialdata_timeline_stops_on_repeated_cursor() -> None:
    calls = {"timeline": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/twitter/user/2/tweets-and-replies":
            calls["timeline"] += 1
            assert "limit" not in request.url.params
            return httpx.Response(
                200,
                json={
                    "data": [],
                    "next_cursor": "same-cursor",
                },
            )
        raise AssertionError(f"Unexpected URL: {request.url}")

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.socialdata.tools")
    api = SocialDataApiClient(token="test", client=client)

    payload = api.get_user_timeline(
        user={"id": "2", "username": "u2", "name": "U2"},
        time_range=TimeRange(
            since=datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc),
            until=datetime(2026, 3, 10, 2, 0, tzinfo=timezone.utc),
        ),
        include_replies=True,
    )

    assert payload.tweets == []
    assert calls["timeline"] == 2
    api.close()


def test_socialdata_timeline_stops_when_page_is_older_than_since() -> None:
    calls = {"timeline": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/twitter/user/2/tweets-and-replies":
            calls["timeline"] += 1
            assert "limit" not in request.url.params
            return httpx.Response(
                200,
                json={
                    "tweets": [
                        {
                            "id": "100",
                            "user": {"id": "2", "username": "u2", "name": "U2"},
                            "text": "old post",
                            "tweet_created_at": "2026-03-09T23:59:00Z",
                            "referenced_tweets": [],
                        }
                    ],
                    "next_cursor": "cursor-should-not-be-used",
                },
            )
        raise AssertionError(f"Unexpected URL: {request.url}")

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.socialdata.tools")
    api = SocialDataApiClient(token="test", client=client)

    payload = api.get_user_timeline(
        user={"id": "2", "username": "u2", "name": "U2"},
        time_range=TimeRange(
            since=datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc),
            until=datetime(2026, 3, 10, 2, 0, tzinfo=timezone.utc),
        ),
        include_replies=True,
    )

    assert payload.tweets == []
    assert calls["timeline"] == 1
    api.close()


def test_socialdata_timeline_stops_when_created_at_is_twitter_date_format() -> None:
    calls = {"timeline": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/twitter/user/2/tweets-and-replies":
            calls["timeline"] += 1
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "100",
                            "author_id": "2",
                            "text": "old post",
                            "created_at": "Thu Mar 12 23:00:00 +0000 2026",
                            "referenced_tweets": [],
                        }
                    ],
                    "next_cursor": "cursor-should-not-be-used",
                },
            )
        raise AssertionError(f"Unexpected URL: {request.url}")

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.socialdata.tools")
    api = SocialDataApiClient(token="test", client=client)

    payload = api.get_user_timeline(
        user={"id": "2", "username": "u2", "name": "U2"},
        time_range=TimeRange(
            since=datetime(2026, 3, 13, 0, 0, tzinfo=timezone.utc),
            until=datetime(2026, 3, 13, 2, 0, tzinfo=timezone.utc),
        ),
        include_replies=True,
    )

    assert payload.tweets == []
    assert calls["timeline"] == 1
    api.close()


def test_socialdata_timeline_page_cap_prevents_excessive_calls() -> None:
    calls = {"timeline": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/twitter/user/2/tweets-and-replies":
            calls["timeline"] += 1
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": str(calls["timeline"]),
                            "author_id": "2",
                            "text": "post",
                            # Keep an unparsable time so lower-bound cutoff does not trigger.
                            "created_at": "unparsable",
                        }
                    ],
                    "next_cursor": f"cursor-{calls['timeline']}",
                },
            )
        raise AssertionError(f"Unexpected URL: {request.url}")

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.socialdata.tools")
    api = SocialDataApiClient(token="test", client=client, max_timeline_pages=3)

    payload = api.get_user_timeline(
        user={"id": "2", "username": "u2", "name": "U2"},
        time_range=TimeRange(
            since=datetime(2026, 3, 13, 0, 0, tzinfo=timezone.utc),
            until=datetime(2026, 3, 13, 2, 0, tzinfo=timezone.utc),
        ),
        include_replies=True,
    )

    assert calls["timeline"] == 3
    assert len(payload.tweets) == 3
    api.close()


def test_socialdata_timeline_stale_old_pages_cap_prevents_waste() -> None:
    calls = {"timeline": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/twitter/user/2/tweets-and-replies":
            calls["timeline"] += 1
            return httpx.Response(
                200,
                json={
                    "tweets": [
                        # Repeated recent item (e.g., pinned/duplicated across pages).
                        {
                            "id": "recent-fixed",
                            "author_id": "2",
                            "text": "recent",
                            "tweet_created_at": "2026-03-13T01:00:00Z",
                        },
                        # Old unique item changes by page.
                        {
                            "id": f"old-{calls['timeline']}",
                            "author_id": "2",
                            "text": "old",
                            "tweet_created_at": "2026-03-11T01:00:00Z",
                        },
                    ],
                    "next_cursor": f"cursor-{calls['timeline']}",
                },
            )
        raise AssertionError(f"Unexpected URL: {request.url}")

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.socialdata.tools")
    api = SocialDataApiClient(
        token="test",
        client=client,
        max_timeline_pages=100,
        max_stale_old_pages=3,
    )

    payload = api.get_user_timeline(
        user={"id": "2", "username": "u2", "name": "U2"},
        time_range=TimeRange(
            since=datetime(2026, 3, 13, 0, 0, tzinfo=timezone.utc),
            until=datetime(2026, 3, 13, 2, 0, tzinfo=timezone.utc),
        ),
        include_replies=True,
    )

    assert calls["timeline"] == 4
    assert "recent-fixed" in {item["id"] for item in payload.tweets}
    api.close()


def test_socialdata_followings_use_friends_list_path() -> None:
    calls: list[tuple[str | None, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/twitter/friends/list":
            calls.append((request.url.params.get("user_id"), request.url.params.get("cursor")))
            if request.url.params.get("cursor") is None:
                return httpx.Response(
                    200,
                    json={
                        "data": [
                            {"id": "200", "username": "u200", "name": "U200"},
                        ],
                        "next_cursor": "next-1",
                    },
                )
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "201", "username": "u201", "name": "U201"},
                    ],
                },
            )
        raise AssertionError(f"Unexpected URL: {request.url}")

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.socialdata.tools")
    api = SocialDataApiClient(token="test", client=client)
    followings = api.get_followings("100", limit=2)

    assert [item["id"] for item in followings] == ["200", "201"]
    assert calls == [("100", None), ("100", "next-1")]
    api.close()


def test_socialdata_user_metrics_mapping() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/twitter/user/demo":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "id": "10",
                        "username": "demo",
                        "name": "Demo",
                        "followers_count": 1234,
                        "friends_count": 88,
                        "statuses_count": 55,
                    }
                },
            )
        raise AssertionError(f"Unexpected URL: {request.url}")

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.socialdata.tools")
    api = SocialDataApiClient(token="test", client=client)
    user = api.get_user_by_username("demo")

    assert user["public_metrics"]["followers_count"] == 1234
    assert user["public_metrics"]["following_count"] == 88
    assert user["public_metrics"]["tweet_count"] == 55
    api.close()
