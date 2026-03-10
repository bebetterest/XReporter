from __future__ import annotations

from datetime import datetime, timedelta, timezone

from xreporter.models import TimeRange


ALLOWED_LAST_RANGES = {
    "12h": timedelta(hours=12),
    "24h": timedelta(hours=24),
}


class TimeRangeError(ValueError):
    """Raised when time range input is invalid."""


def _parse_iso_to_utc(value: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        local_tz = datetime.now().astimezone().tzinfo
        if local_tz is None:
            local_tz = timezone.utc
        dt = dt.replace(tzinfo=local_tz)
    return dt.astimezone(timezone.utc)


def parse_time_range(
    *,
    last: str | None,
    since: str | None,
    until: str | None,
    now: datetime | None = None,
) -> TimeRange:
    current = now or datetime.now(timezone.utc)

    if last and (since or until):
        raise TimeRangeError("Use either --last or --since/--until, not both.")

    if (since and not until) or (until and not since):
        raise TimeRangeError("Both --since and --until are required for absolute time range.")

    if last:
        if last not in ALLOWED_LAST_RANGES:
            raise TimeRangeError("--last only supports 12h and 24h.")
        delta = ALLOWED_LAST_RANGES[last]
        return TimeRange(since=current - delta, until=current)

    if since and until:
        since_dt = _parse_iso_to_utc(since)
        until_dt = _parse_iso_to_utc(until)
        if since_dt >= until_dt:
            raise TimeRangeError("--since must be earlier than --until.")
        return TimeRange(since=since_dt, until=until_dt)

    return TimeRange(since=current - timedelta(hours=24), until=current)
