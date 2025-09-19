"""Date helpers for month normalization."""
from __future__ import annotations

from datetime import date, datetime, timezone

def normalize_month(value: date | datetime) -> datetime:
    """Return the UTC month start for the given date or datetime."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)
        return value.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # date instance
    return datetime(value.year, value.month, 1, tzinfo=timezone.utc)


def current_month_start() -> datetime:
    """Return the UTC start of the current month."""
    return normalize_month(datetime.now(timezone.utc))
