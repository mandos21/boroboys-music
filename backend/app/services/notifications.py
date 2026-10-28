"""Round membership and capacity checks shared by notification delivery."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Round, RoundMember, Submission, SubmissionStatus, User


def reminder_recipients(db: Session, round_: Round) -> list[User]:
    members = list(
        db.execute(
            select(RoundMember, User)
            .join(User, User.id == RoundMember.user_id)
            .where(
                RoundMember.round_id == round_.id,
                RoundMember.removed_at.is_(None),
                RoundMember.declined_further_submissions_at.is_(None),
                User.notify_reminder_emails.is_(True),
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
