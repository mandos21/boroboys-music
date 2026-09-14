"""The router every admin module shares, and the helpers more than one uses."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import DbSession, require_csrf_for_writes
from app.api.payloads import round_timeline
from app.db.models import (
    ExternalAccount,
    ExternalProvider,
    PlatformRole,
    Round,
    Series,
    User,
)
from app.services.authorization import is_series_admin

# One router, imported by each admin module, so route registration order stays
# the order the modules are imported in __init__.
router = APIRouter(
    prefix="/admin", tags=["administration"], dependencies=[Depends(require_csrf_for_writes)]
)


def _require_publishable_account(
    db: DbSession, series_id: uuid.UUID, account_id: uuid.UUID
) -> ExternalAccount:
    """Accept a scheduled publisher only if a series administrator owns it.

    A round publishes to this account without anyone present, so the account
    must belong to somebody who could have published the round by hand.
    """
    account = db.get(ExternalAccount, account_id)
    if account is None or account.provider is not ExternalProvider.SPOTIFY or not account.is_active:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="a connected Spotify account is required to publish automatically",
        )
    owner = db.get(User, account.user_id)
    if owner is None or not is_series_admin(db, series_id, owner):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="the publishing account must belong to a series administrator",
        )
    return account


def _require_platform_admin(user: User) -> None:
    if user.platform_role is not PlatformRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="platform admin required")


def _require_series_admin(db: DbSession, user: User, series_id: uuid.UUID) -> Series:
    series = db.get(Series, series_id)
    if series is None:
        raise _not_found("series")
    if not is_series_admin(db, series_id, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="series admin required")
    return series


def _require_user(db: DbSession, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise _not_found("user")
    return user


def _not_found(resource: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{resource} not found")


def _series_summary(series: Series) -> dict[str, object]:
    return {
        "id": str(series.id),
        "name": series.name,
        "slug": series.slug,
        "description": series.description,
        "timezone": series.timezone,
        "defaultPolicies": series.default_policies,
        "roundPlan": series.round_plan,
        "autoStartNextRound": series.auto_start_next_round,
        "isArchived": series.is_archived,
        "coverImageUrl": series.cover_image_url,
        "accentColor": series.accent_color,
        "defaultAttributionRevealDelaySeconds": series.default_attribution_reveal_delay_seconds,
    }


def _round_summary(round_: Round) -> dict[str, object]:
    return {
        **round_timeline(round_),
        "submissionLimit": round_.submission_limit,
        "publisherAccountId": (
            str(round_.publisher_account_id) if round_.publisher_account_id else None
        ),
        "attributionRevealDelaySeconds": round_.attribution_reveal_delay_seconds,
    }


def _user_summary(user: User) -> dict[str, object]:
    return {
        "id": str(user.id),
        "displayName": user.display_name,
        "email": user.email,
    }
