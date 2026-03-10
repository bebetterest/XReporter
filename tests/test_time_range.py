from datetime import datetime, timezone

import pytest

from xreporter.time_range import TimeRangeError, parse_time_range


def test_parse_last_12h() -> None:
    now = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)
    result = parse_time_range(last="12h", since=None, until=None, now=now)
    assert result.until == now
    assert result.since == datetime(2026, 3, 10, 0, 0, tzinfo=timezone.utc)


def test_parse_last_24h() -> None:
    now = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc)
    result = parse_time_range(last="24h", since=None, until=None, now=now)
    assert result.since == datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)


def test_parse_absolute() -> None:
    result = parse_time_range(
        last=None,
        since="2026-03-09T00:00:00+08:00",
        until="2026-03-10T00:00:00+08:00",
    )
    assert result.since.isoformat() == "2026-03-08T16:00:00+00:00"
    assert result.until.isoformat() == "2026-03-09T16:00:00+00:00"


@pytest.mark.parametrize(
    "last,since,until",
    [
        ("12h", "2026-03-09T00:00:00Z", "2026-03-10T00:00:00Z"),
        (None, "2026-03-10T00:00:00Z", None),
        ("18h", None, None),
    ],
)
def test_parse_invalid(last: str | None, since: str | None, until: str | None) -> None:
    with pytest.raises(TimeRangeError):
        parse_time_range(last=last, since=since, until=until)
