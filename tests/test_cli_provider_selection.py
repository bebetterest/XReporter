from pathlib import Path
from typing import cast

import pytest
import typer

from xreporter.cli import _build_api_client
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
        def __init__(self, token: str, retry_callback=None) -> None:  # type: ignore[no-untyped-def]
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
        def __init__(self, token: str, retry_callback=None) -> None:  # type: ignore[no-untyped-def]
            called["token"] = token

    monkeypatch.delenv("XREPORTER_FIXTURE_FILE", raising=False)
    monkeypatch.setenv("SOCIALDATA_API_KEY", "sd-key")
    monkeypatch.setattr("xreporter.cli.SocialDataApiClient", DummySocialData)

    provider, client = _build_api_client(_cfg(tmp_path, "socialdata"))
    assert provider == "socialdata"
    assert isinstance(client, DummySocialData)
    assert called["token"] == "sd-key"


def test_build_official_provider_requires_token(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("XREPORTER_FIXTURE_FILE", raising=False)
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)

    with pytest.raises(typer.BadParameter, match="X_BEARER_TOKEN"):
        _build_api_client(_cfg(tmp_path, "official"))
