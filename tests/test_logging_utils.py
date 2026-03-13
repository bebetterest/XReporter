from __future__ import annotations

from pathlib import Path

from xreporter.logging_utils import get_logger, setup_logging


def test_setup_logging_creates_log_file_and_writes_entries(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    log_path = setup_logging(log_dir)
    logger = get_logger("test.logging")

    logger.info("test log entry value=%s", 42)
    for handler in logger.handlers:
        handler.flush()
    for handler in get_logger("xreporter").handlers:
        handler.flush()

    assert log_path.exists()
    content = log_path.read_text(encoding="utf-8")
    assert "logging initialized" in content
    assert "test log entry value=42" in content
