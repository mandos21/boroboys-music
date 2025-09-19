from datetime import date, datetime, timezone

from app.core.dates import normalize_month


def test_normalize_month_from_date():
    normalized = normalize_month(date(2024, 5, 20))
    assert normalized == datetime(2024, 5, 1, tzinfo=timezone.utc)


def test_normalize_month_from_datetime():
    source = datetime(2024, 5, 20, 15, 30, 45)
    normalized = normalize_month(source)
    assert normalized == datetime(2024, 5, 1, tzinfo=timezone.utc)
