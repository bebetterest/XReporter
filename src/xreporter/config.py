from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


def default_home_dir() -> Path:
    env_home = os.getenv("XREPORTER_HOME")
    if env_home:
        return Path(env_home).expanduser()
    return Path.home() / ".xreporter"


def default_config_path() -> Path:
    env_path = os.getenv("XREPORTER_CONFIG")
    if env_path:
        return Path(env_path).expanduser()
    return default_home_dir() / "config.toml"


def default_db_path() -> Path:
    return default_home_dir() / "xreporter.db"


def default_report_dir() -> Path:
    return default_home_dir() / "reports"


@dataclass
class AppConfig:
    username: str
    language: str = "auto"
    db_path: str = field(default_factory=lambda: str(default_db_path()))
    report_dir: str = field(default_factory=lambda: str(default_report_dir()))
    following_cap_default: int = 200
    include_replies_default: bool = True


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def save_config(config: AppConfig, path: Path | None = None) -> Path:
    target = path or default_config_path()
    _ensure_parent(target)

    lines = [
        f"username = {json.dumps(config.username)}",
        f"language = {json.dumps(config.language)}",
        f"db_path = {json.dumps(config.db_path)}",
        f"report_dir = {json.dumps(config.report_dir)}",
        f"following_cap_default = {config.following_cap_default}",
        f"include_replies_default = {str(config.include_replies_default).lower()}",
    ]

    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def load_config(path: Path | None = None) -> AppConfig:
    target = path or default_config_path()
    if not target.exists():
        raise FileNotFoundError(f"Config file not found: {target}")

    data = tomllib.loads(target.read_text(encoding="utf-8"))
    username = str(data.get("username", "")).strip()
    if not username:
        raise ValueError("Config field 'username' is required.")

    language = str(data.get("language", "auto"))
    if language not in {"auto", "en", "zh"}:
        language = "auto"

    following_cap_default = int(data.get("following_cap_default", 200))
    if following_cap_default <= 0:
        raise ValueError("following_cap_default must be > 0")

    include_replies_default = bool(data.get("include_replies_default", True))

    return AppConfig(
        username=username,
        language=language,
        db_path=str(data.get("db_path", default_db_path())),
        report_dir=str(data.get("report_dir", default_report_dir())),
        following_cap_default=following_cap_default,
        include_replies_default=include_replies_default,
    )


def config_exists(path: Path | None = None) -> bool:
    return (path or default_config_path()).exists()
