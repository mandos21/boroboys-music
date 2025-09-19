from datetime import date, datetime

from app.services.playlist_manager import _normalize_month


def test_normalize_month_from_date():
    normalized = _normalize_month(date(2024, 5, 20))
    assert normalized == datetime(2024, 5, 1)


def test_normalize_month_from_datetime():
    source = datetime(2024, 5, 20, 15, 30, 45)
    normalized = _normalize_month(source)
    assert normalized == datetime(2024, 5, 1)