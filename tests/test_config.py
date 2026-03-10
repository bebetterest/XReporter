from pathlib import Path

import pytest

from xreporter.config import AppConfig, default_twscrape_accounts_db_path, load_config, save_config


def test_config_roundtrip_with_provider_fields(tmp_path: Path) -> None:
    cfg = AppConfig(
        username="target",
        language="en",
        db_path=str(tmp_path / "xreporter.db"),
        report_dir=str(tmp_path / "reports"),
        following_cap_default=123,
        include_replies_default=False,
        api_provider="socialdata",
        twscrape_accounts_db_path=str(tmp_path / "accounts.db"),
    )
    path = tmp_path / "config.toml"
    save_config(cfg, path=path)

    loaded = load_config(path=path)
    assert loaded.username == "target"
    assert loaded.api_provider == "socialdata"
    assert loaded.twscrape_accounts_db_path == str(tmp_path / "accounts.db")
    assert loaded.following_cap_default == 123
    assert loaded.include_replies_default is False


def test_legacy_config_defaults_to_official_provider(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        "\n".join(
            [
                'username = "target"',
                'language = "auto"',
                "following_cap_default = 200",
                "include_replies_default = true",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    loaded = load_config(path=path)
    assert loaded.api_provider == "official"
    assert loaded.twscrape_accounts_db_path == str(default_twscrape_accounts_db_path())


def test_invalid_provider_raises(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        "\n".join(
            [
                'username = "target"',
                'api_provider = "invalid"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="api_provider"):
        load_config(path=path)
