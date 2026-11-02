"""Read-side authorization predicates shared by the API layer.

These answer questions about durable domain state rather than about HTTP, so
they live beside the other services and raise nothing. Routes decide what a
false answer means: a 403, a narrowed query, or a hidden control.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

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


def is_series_admin(db: Session, series_id: uuid.UUID, user: User) -> bool:
    """A platform administrator administers every series implicitly."""
    if user.platform_role is PlatformRole.ADMIN:
        return True
    return (
        db.scalar(
            select(SeriesAdmin.id).where(
                SeriesAdmin.series_id == series_id,
                SeriesAdmin.user_id == user.id,
            )
        )
        is not None
    )


def is_round_member(db: Session, round_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Membership is the active kind; a removed contributor is not a member."""
    return (
        db.scalar(
            select(RoundMember.id).where(
                RoundMember.round_id == round_id,
                RoundMember.user_id == user_id,
                RoundMember.removed_at.is_(None),
            )
        )
        is not None
    )


def accessible_series(user: User) -> Select[tuple[Series]]:
    """Series visible through administration, group membership, or an active round membership."""
    statement = select(Series).order_by(Series.name, Series.id)
    if user.platform_role is PlatformRole.ADMIN:
        return statement
    return statement.where(
        or_(
            select(SeriesAdmin.id)
            .where(SeriesAdmin.series_id == Series.id, SeriesAdmin.user_id == user.id)
            .exists(),
            select(ContributorGroupMember.id)
            .join(ContributorGroup)
            .where(
                ContributorGroup.series_id == Series.id, ContributorGroupMember.user_id == user.id
            )
            .exists(),
            select(RoundMember.id)
            .join(Round)
            .where(
                Round.series_id == Series.id,
                RoundMember.user_id == user.id,
                RoundMember.removed_at.is_(None),
            )
            .exists(),
        )
    )
