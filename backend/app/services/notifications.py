"""Round membership and capacity checks shared by notification delivery."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.db.models import (
    Round,
    RoundMember,
    SeriesNotificationPreference,
    Submission,
    SubmissionStatus,
    User,
)


def email_preference_allows(
    series_id: uuid.UUID, *, published: bool = False
) -> ColumnElement[bool]:
    """Global opt-outs win; a missing series preference preserves the default opt-in."""
    global_preference = (
        User.notify_round_published_emails if published else User.notify_reminder_emails
    )
    series_preference = (
        SeriesNotificationPreference.notify_round_published_emails
        if published
        else SeriesNotificationPreference.notify_reminder_emails
    )
    opted_out = (
        select(SeriesNotificationPreference.id)
        .where(
            SeriesNotificationPreference.user_id == User.id,
            SeriesNotificationPreference.series_id == series_id,
            series_preference.is_(False),
        )
        .exists()
    )
    return global_preference.is_(True) & ~opted_out


def reminder_recipients(db: Session, round_: Round) -> list[User]:
    members = list(
        db.execute(
            select(RoundMember, User)
            .join(User, User.id == RoundMember.user_id)
            .where(
                RoundMember.round_id == round_.id,
                RoundMember.removed_at.is_(None),
                RoundMember.declined_further_submissions_at.is_(None),
                email_preference_allows(round_.series_id),
                User.is_active.is_(True),
                User.email.is_not(None),
            )
        )
    )
    if not members:
        return []
    counts: dict[uuid.UUID, int] = dict(
        db.execute(
            select(Submission.contributor_id, func.count())
            .where(
                Submission.round_id == round_.id,
                Submission.status == SubmissionStatus.ACCEPTED,
                Submission.contributor_id.in_([member.user_id for member, _ in members]),
            )
            .group_by(Submission.contributor_id)
        )
        .tuples()
        .all()
    )
    recipients = []
    for member, user in members:
        limit = (
            member.submission_limit_override
            if member.submission_limit_override is not None
            else round_.submission_limit
        )
        if counts.get(user.id, 0) < limit:
            recipients.append(user)
    return recipients
