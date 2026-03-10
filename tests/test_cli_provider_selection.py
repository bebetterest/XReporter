import sqlite3
from pathlib import Path
from typing import cast

import pytest
import typer

from xreporter.cli import _build_api_client, _provider_credential_status
from xreporter.config import APIProvider, AppConfig


def _cfg(tmp_path: Path, provider: str) -> AppConfig:
    return AppConfig(
        username="target",
        language="en",
        db_path=str(tmp_path / "xreporter.db"),
        report_dir=str(tmp_path / "reports"),
        following_cap_default=100,
        include_replies_default=True,
        api_provider=cast(APIProvider, provider),
        twscrape_accounts_db_path=str(tmp_path / "accounts.db"),
    )


def test_fixture_has_priority_over_provider(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fixture_file = tmp_path / "fixture.json"
    fixture_file.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("XREPORTER_FIXTURE_FILE", str(fixture_file))

    provider, client = _build_api_client(_cfg(tmp_path, "official"))
    assert provider == "fixture"
    assert client.__class__.__name__ == "FixtureXApiClient"


def test_build_official_provider(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    called: dict[str, str] = {}

    class DummyOfficial:
        def __init__(self, token: str) -> None:
            called["token"] = token

    monkeypatch.delenv("XREPORTER_FIXTURE_FILE", raising=False)
    monkeypatch.setenv("X_BEARER_TOKEN", "token-1")
    monkeypatch.setattr("xreporter.cli.XApiClient", DummyOfficial)

    provider, client = _build_api_client(_cfg(tmp_path, "official"))
    assert provider == "official"
    assert isinstance(client, DummyOfficial)
    assert called["token"] == "token-1"


def test_build_socialdata_provider(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    called: dict[str, str] = {}

    class DummySocialData:
        def __init__(self, token: str) -> None:
            called["token"] = token

    monkeypatch.delenv("XREPORTER_FIXTURE_FILE", raising=False)
    monkeypatch.setenv("SOCIALDATA_API_KEY", "sd-key")
    monkeypatch.setattr("xreporter.cli.SocialDataApiClient", DummySocialData)

    provider, client = _build_api_client(_cfg(tmp_path, "socialdata"))
    assert provider == "socialdata"
    assert isinstance(client, DummySocialData)
    assert called["token"] == "sd-key"


def test_build_twscrape_provider(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    called: dict[str, str] = {}

    class DummyTwscrape:
        def __init__(self, accounts_db_path: Path) -> None:
            called["path"] = str(accounts_db_path)

    monkeypatch.delenv("XREPORTER_FIXTURE_FILE", raising=False)
    monkeypatch.setattr("xreporter.cli.TwscrapeApiClient", DummyTwscrape)

    provider, client = _build_api_client(_cfg(tmp_path, "twscrape"))
    assert provider == "twscrape"
    assert isinstance(client, DummyTwscrape)
    assert called["path"] == str(tmp_path / "accounts.db")


def test_build_official_provider_requires_token(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("XREPORTER_FIXTURE_FILE", raising=False)
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)

    with pytest.raises(typer.BadParameter, match="X_BEARER_TOKEN"):
        _build_api_client(_cfg(tmp_path, "official"))


def test_twscrape_credential_status_allows_existing_pool_without_email(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    accounts_db = tmp_path / "accounts.db"
    with sqlite3.connect(accounts_db) as conn:
        conn.execute("CREATE TABLE accounts (username TEXT)")
        conn.execute("INSERT INTO accounts (username) VALUES ('existing-user')")
        conn.commit()

    monkeypatch.setenv("XREPORTER_TWS_USERNAME", "user")
    monkeypatch.setenv("XREPORTER_TWS_PASSWORD", "pass")
    monkeypatch.delenv("XREPORTER_TWS_EMAIL", raising=False)
    monkeypatch.delenv("XREPORTER_TWS_EMAIL_PASSWORD", raising=False)

    ok, detail = _provider_credential_status(
        "twscrape",
        False,
        twscrape_accounts_db_path=accounts_db,
    )
    assert ok is True
    assert "existing account pool" in detail
