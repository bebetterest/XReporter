from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import Lock


_LOCK = Lock()
_CONFIGURED_PATH: Path | None = None


def _resolve_level() -> int:
    level_name = os.getenv("XREPORTER_LOG_LEVEL", "INFO").strip().upper()
    return int(getattr(logging, level_name, logging.INFO))


def setup_logging(log_dir: Path) -> Path:
    global _CONFIGURED_PATH

    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "xreporter.log"

    with _LOCK:
        if _CONFIGURED_PATH == log_path:
            return log_path

        logger = logging.getLogger("xreporter")
        logger.handlers.clear()
        logger.propagate = False

        level = _resolve_level()
        logger.setLevel(level)

        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )

        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        stderr_flag = os.getenv("XREPORTER_LOG_STDERR", "").strip().lower()
        if stderr_flag in {"1", "true", "yes", "on"}:
            stream_handler = logging.StreamHandler()
            stream_handler.setLevel(level)
            stream_handler.setFormatter(formatter)
            logger.addHandler(stream_handler)

        _CONFIGURED_PATH = log_path
        logger.info(
            "logging initialized log_path=%s level=%s",
            log_path,
            logging.getLevelName(level),
        )

    return log_path


def get_logger(name: str) -> logging.Logger:
    if name.startswith("xreporter"):
        return logging.getLogger(name)
    return logging.getLogger(f"xreporter.{name}")
