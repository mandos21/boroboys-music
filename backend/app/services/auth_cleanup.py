"""Bounded retention for expired browser and provider-link state."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db.models import ExternalLinkAttempt, OidcLoginAttempt, ServerSession


def purge_expired_auth_state(db: Session, now: datetime | None = None) -> None:
    """Remove expired credentials and one-time states after a short grace period."""
    instant = now or datetime.now(UTC)
    # Retain consumed attempts briefly for support/debugging, but never retain
    # encrypted OIDC tokens in expired server sessions indefinitely.
    attempt_cutoff = instant - timedelta(days=1)
    db.execute(delete(ServerSession).where(ServerSession.expires_at <= instant))
    db.execute(
        delete(OidcLoginAttempt).where(
            OidcLoginAttempt.expires_at <= attempt_cutoff,
        )
    )
    db.execute(
        delete(ExternalLinkAttempt).where(
            ExternalLinkAttempt.expires_at <= attempt_cutoff,
        )
    )
