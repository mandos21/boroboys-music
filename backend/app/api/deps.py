"""Shared API dependencies for identity, authorization, and CSRF protection."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import secrets_match
from app.db.models import PlatformRole, ServerSession, User
from app.db.session import get_db_session

DbSession = Annotated[Session, Depends(get_db_session)]


SESSION_ACTIVITY_RESOLUTION = timedelta(minutes=5)


def get_current_session(request: Request, db: DbSession) -> ServerSession:
    token = request.cookies.get(get_settings().session_cookie_name)
    if not token:
        raise _unauthenticated()
    now = datetime.now(UTC)
    session = db.scalar(
        select(ServerSession).where(
            ServerSession.token_hash == _hash_for_lookup(token),
            ServerSession.expires_at > now,
        )
    )
    if session is None:
        raise _unauthenticated()
    # Recorded at a coarse resolution so an ordinary page load costs reads, not
    # a write per request, while the column still answers "is this in use".
    if session.last_seen_at < now - SESSION_ACTIVITY_RESOLUTION:
        session.last_seen_at = now
        db.commit()
    return session


def get_current_user(
    session: Annotated[ServerSession, Depends(get_current_session)], db: DbSession
) -> User:
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise _unauthenticated()
    return user


def require_platform_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.platform_role is not PlatformRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="platform admin required")
    return user


def require_csrf(
    request: Request, session: Annotated[ServerSession, Depends(get_current_session)]
) -> None:
    csrf_token = request.headers.get("X-CSRF-Token")
    if not csrf_token or not secrets_match(csrf_token, session.csrf_secret_hash):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid CSRF token")


# Methods that must not change state; a router-wide CSRF dependency has no
# business demanding the token for these.
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def require_csrf_for_writes(
    request: Request, session: Annotated[ServerSession, Depends(get_current_session)]
) -> None:
    """Router-level CSRF: enforced on every unsafe method, skipped for reads."""
    if request.method in _SAFE_METHODS:
        return
    require_csrf(request, session)


def _hash_for_lookup(value: str) -> str:
    # Local import avoids re-exporting implementation details through this module.
    from app.core.security import hash_secret

    return hash_secret(value)


def _unauthenticated() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="authentication required",
        headers={"WWW-Authenticate": "Session"},
    )
