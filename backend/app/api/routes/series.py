"""Contributor-visible series history without leaking other private round groups."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select

from app.api.deps import DbSession, get_current_user
from app.db.models import (
    ContributorGroup,
    ContributorGroupMember,
    PlatformRole,
    Round,
    RoundMember,
    Series,
    SeriesAdmin,
    User,
)
from app.services.lifecycle import reconcile_round_status

router = APIRouter(prefix="/series", tags=["series"])


@router.get("")
def list_my_series(
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> list[dict[str, object]]:
    """List every series a listener can enter, with a useful round preview."""
    if user.platform_role is PlatformRole.ADMIN:
        series_items = list(db.scalars(select(Series).order_by(Series.name)))
    else:
        series_items = list(
            db.scalars(
                select(Series)
                .outerjoin(Round, Round.series_id == Series.id)
                .outerjoin(
                    RoundMember,
                    (RoundMember.round_id == Round.id)
                    & (RoundMember.user_id == user.id)
                    & RoundMember.removed_at.is_(None),
                )
                .outerjoin(
                    SeriesAdmin,
                    (SeriesAdmin.series_id == Series.id) & (SeriesAdmin.user_id == user.id),
                )
                .outerjoin(ContributorGroup, ContributorGroup.series_id == Series.id)
                .outerjoin(
                    ContributorGroupMember,
                    (ContributorGroupMember.group_id == ContributorGroup.id)
                    & (ContributorGroupMember.user_id == user.id),
                )
                .where(
                    or_(
                        RoundMember.id.is_not(None),
                        SeriesAdmin.id.is_not(None),
                        ContributorGroupMember.id.is_not(None),
                    )
                )
                .distinct()
                .order_by(Series.name)
            )
        )
    return [_series_payload(db, series, user) for series in series_items]


@router.get("/{series_id}")
def get_series_history(
    series_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, object]:
    """Return rounds visible to the caller within one series.

    Series may run overlapping contributor groups. A normal contributor sees
    only their active materialized memberships; platform and series admins can
    inspect the complete series history.
    """
    series = db.get(Series, series_id)
    if series is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="series not found")
    is_admin = _is_series_admin(db, series_id, user)
    rounds = _visible_rounds(db, series_id, user, is_admin)
    if not is_admin and not rounds and not _has_series_membership(db, series_id, user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="series access required")
    return {
        "id": str(series.id),
        "name": series.name,
        "description": series.description,
        "timezone": series.timezone,
        "isAdmin": is_admin,
        "rounds": [
            {
                "id": str(round_.id),
                "title": round_.title,
                "status": round_.status.value,
                "opensAt": round_.opens_at.isoformat(),
                "closesAt": round_.closes_at.isoformat(),
                "publishAt": round_.publish_at.isoformat(),
            }
            for round_ in rounds
        ],
    }


def _series_payload(db: DbSession, series: Series, user: User) -> dict[str, object]:
    is_admin = _is_series_admin(db, series.id, user)
    rounds = _visible_rounds(db, series.id, user, is_admin)
    active = next((round_ for round_ in rounds if round_.status.value != "published"), None)
    latest = active or (rounds[0] if rounds else None)
    return {
        "id": str(series.id),
        "name": series.name,
        "description": series.description,
        "timezone": series.timezone,
        "isAdmin": is_admin,
        "featuredRound": _round_payload(latest) if latest else None,
    }


def _visible_rounds(db: DbSession, series_id: uuid.UUID, user: User, is_admin: bool) -> list[Round]:
    statement = select(Round).where(Round.series_id == series_id)
    if not is_admin:
        statement = (
            statement.join(RoundMember, RoundMember.round_id == Round.id)
            .where(RoundMember.user_id == user.id, RoundMember.removed_at.is_(None))
            .distinct()
        )
    rounds = list(db.scalars(statement.order_by(Round.opens_at.desc())))
    if any(reconcile_round_status(round_) for round_ in rounds):
        db.commit()
    return sorted(
        rounds,
        key=lambda round_: (round_.status.value == "published", -round_.opens_at.timestamp()),
    )


def _is_series_admin(db: DbSession, series_id: uuid.UUID, user: User) -> bool:
    return user.platform_role is PlatformRole.ADMIN or (
        db.scalar(
            select(SeriesAdmin.id).where(
                SeriesAdmin.series_id == series_id,
                SeriesAdmin.user_id == user.id,
            )
        )
        is not None
    )


def _has_series_membership(db: DbSession, series_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(ContributorGroupMember.group_id)
            .join(ContributorGroup, ContributorGroup.id == ContributorGroupMember.group_id)
            .where(
                ContributorGroup.series_id == series_id,
                ContributorGroupMember.user_id == user_id,
            )
        )
        is not None
    )


def _round_payload(round_: Round) -> dict[str, object]:
    return {
        "id": str(round_.id),
        "title": round_.title,
        "status": round_.status.value,
        "opensAt": round_.opens_at.isoformat(),
        "closesAt": round_.closes_at.isoformat(),
        "publishAt": round_.publish_at.isoformat(),
    }
