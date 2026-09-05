"""Shared API dependencies for identity, authorization, and CSRF protection."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import secrets_match
from app.db.models import PlatformRole, ServerSession, User
from app.db.session import get_db_session

DbSession = Annotated[Session, Depends(get_db_session)]


def get_current_session(request: Request, db: DbSession) -> ServerSession:
    token = request.cookies.get(get_settings().session_cookie_name)
    if not token:
        raise _unauthenticated()
    session = db.scalar(
        select(ServerSession).where(
            ServerSession.token_hash == _hash_for_lookup(token),
            ServerSession.expires_at > datetime.now(UTC),
        )
    )
    if session is None:
        raise _unauthenticated()
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
