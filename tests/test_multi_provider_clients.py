from __future__ import annotations

from datetime import datetime, timezone

import httpx

from xreporter.models import TimeRange
from xreporter.x_api import SocialDataApiClient


def test_socialdata_retry_then_success() -> None:
    attempts = {"n": 0}
    sleeps: list[float] = []

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
    )

    user = api.get_user_by_username("demo")
    assert user["id"] == "10"
    assert attempts["n"] == 2
    assert sleeps == [1.0]
    api.close()


def test_socialdata_timeline_backfills_referenced_tweets() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/twitter/user/2/tweets-and-replies":
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

        if request.url.path == "/twitter/tweet/999":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "id": "999",
                        "author_id": "30",
                        "text": "origin",
                        "created_at": "2026-03-10T00:30:00Z",
                        "user": {"id": "30", "username": "orig", "name": "Orig"},
                    }
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
