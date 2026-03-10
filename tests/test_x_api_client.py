from datetime import datetime, timezone

import httpx

from xreporter.models import TimeRange
from xreporter.x_api import XApiClient


def test_following_pagination() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path.endswith("/users/1/following"):
            token = request.url.params.get("pagination_token")
            if token is None:
                return httpx.Response(
                    200,
                    json={
                        "data": [
                            {"id": "2", "username": "u2", "name": "U2"},
                            {"id": "3", "username": "u3", "name": "U3"},
                        ],
                        "meta": {"next_token": "next"},
                    },
                )
            return httpx.Response(
                200,
                json={
                    "data": [{"id": "4", "username": "u4", "name": "U4"}],
                    "meta": {},
                },
            )
        raise AssertionError(f"Unexpected URL: {request.url}")

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.x.com/2")
    api = XApiClient(token="test", client=client)
    data = api.get_followings("1", limit=3)
    assert [item["id"] for item in data] == ["2", "3", "4"]
    assert len(calls) == 2
    api.close()


def test_retry_then_success() -> None:
    attempts = {"n": 0}
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/users/by/username/demo"):
            attempts["n"] += 1
            if attempts["n"] == 1:
                return httpx.Response(429, json={"title": "Too Many Requests"})
            return httpx.Response(200, json={"data": {"id": "10", "username": "demo", "name": "Demo"}})
        raise AssertionError(f"Unexpected URL: {request.url}")

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.x.com/2")
    api = XApiClient(
        token="test",
        client=client,
        sleep_func=lambda value: sleeps.append(value),
        random_func=lambda: 0.0,
        max_retries=3,
    )

    user = api.get_user_by_username("demo")
    assert user["id"] == "10"
    assert attempts["n"] == 2
    assert sleeps == [1.0]
    api.close()


def test_fetch_unresolved_referenced_tweets() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/users/2/tweets"):
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
                    ],
                    "includes": {"users": [{"id": "2", "username": "u2", "name": "U2"}], "tweets": []},
                    "meta": {},
                },
            )

        if request.url.path.endswith("/tweets"):
            ids = request.url.params.get("ids")
            assert ids == "999"
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "999",
                            "author_id": "30",
                            "text": "origin",
                            "created_at": "2026-03-10T00:30:00Z",
                        }
                    ],
                    "includes": {"users": [{"id": "30", "username": "orig", "name": "Orig"}]},
                },
            )

        raise AssertionError(f"Unexpected URL: {request.url}")

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.x.com/2")
    api = XApiClient(token="test", client=client)

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
