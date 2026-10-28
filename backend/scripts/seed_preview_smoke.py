"""Seed only a disposable *_test DB for the production-image preview smoke check."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.db.models import Round, RoundStatus, Series
from app.db.session import get_session_factory

database = make_url(get_settings().database_url).database
if not database or not database.endswith("_test"):
    raise SystemExit("Preview smoke fixtures require an isolated *_test database")

with get_session_factory()() as db:
    series = Series(name="Preview smoke series", slug="preview-smoke", timezone="America/New_York")
    db.add(series)
    db.flush()
    now = datetime.now(UTC)
    for identifier, state, title in [
        ("00000000-0000-4000-8000-000000000001", RoundStatus.OPEN, "Preview smoke round"),
        ("00000000-0000-4000-8000-000000000002", RoundStatus.DRAFT, "PRIVATE DRAFT TITLE"),
    ]:
        db.add(
            Round(
                id=UUID(identifier),
                series_id=series.id,
                title=title,
                status=state,
                timezone="America/New_York",
                submission_limit=3,
                opens_at=now - timedelta(days=1),
                closes_at=now + timedelta(days=3),
                publish_at=now + timedelta(days=4),
                prompt="What were your favorite tracks this month?",
            )
        )
    db.commit()
