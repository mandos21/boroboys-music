"""Deadline reminders and round-lifecycle notifications.

Delivery never blocks a caller: every function here is meant to run inside a
Procrastinate task, and a failed send is logged rather than raised, because
one member's bouncing address should never fail the whole notification pass.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import Round, RoundMember, RoundStatus, Submission, SubmissionStatus, User
from app.services import email, mattermost

LOGGER = logging.getLogger(__name__)

# (window key, hours before closing) - checked in this order so a worker that
# was down long enough to cross both thresholds at once sends both reminders
# rather than silently skipping the earlier one.
_REMINDER_WINDOWS: tuple[tuple[str, int], ...] = (("48h", 48), ("24h", 24))


def start_due_reminders(db: Session, now: datetime | None = None) -> list[tuple[uuid.UUID, str]]:
    """Claim each open round's reminder windows exactly once.

    Marking `reminder_<window>_sent_at` here, inside the same transaction that
    selects the round, is what makes this idempotent: a round can only be
    claimed for a given window while that column is still null.
    """
    instant = now or datetime.now(UTC)
    claimed: list[tuple[uuid.UUID, str]] = []
    for window, hours in _REMINDER_WINDOWS:
        column = getattr(Round, f"reminder_{window}_sent_at")
        due = db.scalars(
            select(Round)
            .where(
                Round.status == RoundStatus.OPEN,
                Round.closes_at <= instant + timedelta(hours=hours),
                Round.closes_at > instant,
                column.is_(None),
            )
            .with_for_update(skip_locked=True)
        )
        for round_ in due:
            setattr(round_, f"reminder_{window}_sent_at", instant)
            claimed.append((round_.id, window))
    return claimed


def send_round_reminder(db: Session, round_id: uuid.UUID, window: str) -> None:
    round_ = db.get(Round, round_id)
    if round_ is None:
        return
    hours = dict(_REMINDER_WINDOWS)[window]
    settings = get_settings()
    url = _round_url(settings, round_.id)
    subject = f'{hours} hours left to submit to "{round_.title}"'
    for user in _reminder_recipients(db, round_):
        body = (
            f"Hi {user.display_name or 'there'},\n\n"
            f'"{round_.title}" closes in about {hours} hours. Add your pick before then:\n'
            f"{url}\n\n"
            "You're getting this because you're in this round and haven't used all your "
            "submissions yet. Turn off deadline reminders from your profile settings, or tell "
            "the round you're not submitting more from the round page.\n"
        )
        _try_send_email(settings, user.email, subject, body)


def notify_round_published(db: Session, round_id: uuid.UUID) -> None:
    round_ = db.get(Round, round_id)
    if round_ is None:
        return
    settings = get_settings()
    url = _round_url(settings, round_.id)
    subject = f'"{round_.title}" is published'
    for user in _round_published_recipients(db, round_.id):
        body = (
            f"Hi {user.display_name or 'there'},\n\n"
            f'"{round_.title}" has been published. Give it a listen:\n{url}\n\n'
            "Turn off these emails any time from your profile settings.\n"
        )
        _try_send_email(settings, user.email, subject, body)
    _try_post_mattermost(settings, f'🎧 "{round_.title}" has been published: {url}')


def notify_round_opened(db: Session, round_id: uuid.UUID) -> None:
    round_ = db.get(Round, round_id)
    if round_ is None:
        return
    settings = get_settings()
    url = _round_url(settings, round_.id)
    _try_post_mattermost(settings, f'🎙️ "{round_.title}" is now open for submissions: {url}')


def _reminder_recipients(db: Session, round_: Round) -> list[User]:
    members = list(
        db.execute(
            select(RoundMember, User)
            .join(User, User.id == RoundMember.user_id)
            .where(
                RoundMember.round_id == round_.id,
                RoundMember.removed_at.is_(None),
                RoundMember.declined_further_submissions_at.is_(None),
                User.notify_reminder_emails.is_(True),
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


def _round_published_recipients(db: Session, round_id: uuid.UUID) -> list[User]:
    return list(
        db.scalars(
            select(User)
            .join(RoundMember, RoundMember.user_id == User.id)
            .where(
                RoundMember.round_id == round_id,
                RoundMember.removed_at.is_(None),
                User.notify_round_published_emails.is_(True),
                User.email.is_not(None),
            )
        )
    )


def _round_url(settings: Settings, round_id: uuid.UUID) -> str:
    return f"{str(settings.app_base_url).rstrip('/')}/rounds/{round_id}"


def _try_send_email(settings: Settings, to_address: str | None, subject: str, body: str) -> None:
    if not to_address or not settings.smtp_is_configured:
        return
    try:
        email.send_email(settings, to_address, subject, body)
    except email.EmailError:
        LOGGER.exception("notification email failed", extra={"to": to_address})


def _try_post_mattermost(settings: Settings, text: str) -> None:
    if not settings.mattermost_is_configured:
        return
    try:
        mattermost.post_message(settings, text)
    except mattermost.MattermostError:
        LOGGER.exception("mattermost post failed")
