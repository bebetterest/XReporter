from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest

from xreporter.models import TimeRange
from xreporter.x_api import SocialDataApiClient, TwscrapeApiClient


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


class _FakePool:
    def __init__(self) -> None:
        self.added: list[tuple[str, str, str, str]] = []
        self.logged_in = False

    async def add_account(self, username: str, password: str, email: str, email_password: str) -> None:
        self.added.append((username, password, email, email_password))

    async def login_all(self) -> None:
        self.logged_in = True


class _FakeTwsApi:
    def __init__(self) -> None:
        self.pool = _FakePool()

    async def user_by_login(self, username: str) -> dict[str, Any]:
        return {"id": "10", "username": username, "name": "Demo"}

    def following(self, user_id: Any, limit: int = 20):  # noqa: ANN401
        async def _gen():
            yield {"id": "2", "username": "u2", "name": "U2"}
            yield {"id": "3", "username": "u3", "name": "U3"}

        return _gen()

    def user_tweets(self, user_id: Any):  # noqa: ANN401
        async def _gen():
            yield {
                "id": "200",
                "userId": "2",
                "rawContent": "rt",
                "date": "2026-03-10T01:00:00Z",
                "retweetedTweetId": "999",
                "stats": {"likes": 1, "retweets": 0, "replies": 0, "quotes": 0},
            }

        return _gen()

    async def tweet_details(self, tweet_id: Any) -> dict[str, Any]:  # noqa: ANN401
        return {
            "id": str(tweet_id),
            "userId": "30",
            "rawContent": "origin",
            "date": "2026-03-10T00:30:00Z",
        }


def test_twscrape_client_collects_followings_and_backfills(tmp_path: Path) -> None:
    api = _FakeTwsApi()
    client = TwscrapeApiClient(
        accounts_db_path=tmp_path / "accounts.db",
        username="user",
        password="pass",
        email="mail@example.com",
        email_password="mail-pass",
        api=api,
        auto_login=True,
    )

    user = client.get_user_by_username("demo")
    assert user["id"] == "10"

    followings = client.get_followings("10", limit=1)
    assert [item["id"] for item in followings] == ["2"]

    payload = client.get_user_timeline(
        user={"id": "2", "username": "u2", "name": "U2"},
        time_range=TimeRange(
            since=datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc),
            until=datetime(2026, 3, 10, 2, 0, tzinfo=timezone.utc),
        ),
        include_replies=True,
    )

    assert "999" in payload.include_tweets
    assert payload.include_tweets["999"]["text"] == "origin"
    assert api.pool.logged_in is True
    assert len(api.pool.added) == 1


def test_twscrape_requires_credentials(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("XREPORTER_TWS_USERNAME", raising=False)
    monkeypatch.delenv("XREPORTER_TWS_PASSWORD", raising=False)
    monkeypatch.delenv("XREPORTER_TWS_EMAIL", raising=False)
    monkeypatch.delenv("XREPORTER_TWS_EMAIL_PASSWORD", raising=False)

    with pytest.raises(ValueError, match="Missing twscrape credentials"):
        TwscrapeApiClient(
            accounts_db_path=tmp_path / "accounts.db",
            api=_FakeTwsApi(),
            auto_login=True,
        )
