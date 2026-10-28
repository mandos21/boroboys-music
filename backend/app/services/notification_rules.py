"""Per-series notification rules, scheduling, and durable per-recipient delivery.

The scheduler commits delivery rows before queueing work. Each worker locks one
recipient until delivery completes. A crashed enqueue is recovered next minute;
normal retries never repeat recipients that already succeeded. As with any SMTP
or webhook sender, a crash after provider acceptance but before commit can repeat
a message: neither provider exposes an idempotency key.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from string import Formatter
from typing import Literal
from zoneinfo import ZoneInfo

from cryptography.fernet import InvalidToken
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import decrypt
from app.db.models import (
    NotificationDelivery,
    NotificationEvent,
    NotificationRule,
    Publication,
    PublicationState,
    Round,
    RoundMember,
    RoundStatus,
    Series,
    User,
)
from app.services import email, mattermost
from app.services.notifications import reminder_recipients

Channel = Literal["email", "mattermost"]
Milestone = Literal["opens", "closes", "scheduled_release", "published"]
Audience = Literal["members", "remaining"]
FIELDS = ("series_name", "round_title", "round_url", "opens_at", "closes_at", "publishes_at")
MAX_ATTEMPTS = 5


class RuleInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    enabled: bool = True
    channel: Channel
    milestone: Milestone
    offset_minutes: int = Field(default=0, ge=-43200, le=43200)
    audience: Audience = "members"
    message_template: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def validate_rule(self) -> RuleInput:
        self.name = self.name.strip()
        self.message_template = self.message_template.strip()
        if not self.name or not self.message_template:
            raise ValueError("A name and message are required")
        if self.milestone == "published" and self.offset_minutes < 0:
            raise ValueError("Use scheduled release for messages before publication")
        if self.audience == "remaining" and (
            self.channel != "email"
            or not (
                (self.milestone == "opens" and self.offset_minutes >= 0)
                or (self.milestone == "closes" and self.offset_minutes < 0)
            )
        ):
            raise ValueError("Members with room can only receive email while submissions are open")
        for _, field, spec, conversion in Formatter().parse(self.message_template):
            if field is not None and (field not in FIELDS or spec or conversion):
                raise ValueError("Use only supported message fields: " + ", ".join(FIELDS))
        return self


DEFAULT_RULES = (
    dict(
        name="Round opens",
        channel="mattermost",
        milestone="opens",
        offset_minutes=0,
        audience="members",
        message_template='🎙️ "{round_title}" is open for submissions: {round_url}',
    ),
    dict(
        name="Two-day reminder",
        channel="email",
        milestone="closes",
        offset_minutes=-2880,
        audience="remaining",
        message_template=(
            '"{round_title}" closes on {closes_at}. There is still room for your picks: {round_url}'
        ),
    ),
    dict(
        name="One-day reminder",
        channel="email",
        milestone="closes",
        offset_minutes=-1440,
        audience="remaining",
        message_template=(
            'Last day to share your picks for "{round_title}". '
            "Submissions close on {closes_at}: {round_url}"
        ),
    ),
    dict(
        name="Playlist published",
        channel="mattermost",
        milestone="published",
        offset_minutes=0,
        audience="members",
        message_template='🎧 "{round_title}" has been published. Give it a listen: {round_url}',
    ),
    dict(
        name="Playlist published",
        channel="email",
        milestone="published",
        offset_minutes=0,
        audience="members",
        message_template='"{round_title}" has been published. Give it a listen: {round_url}',
    ),
)


def seed_rules(db: Session, series: Series) -> None:
    for values in DEFAULT_RULES:
        db.add(
            NotificationRule(series_id=series.id, **RuleInput.model_validate(values).model_dump())
        )


def scheduled_at(
    rule: NotificationRule | RuleInput, round_: Round, publication: Publication | None
) -> datetime | None:
    milestone = {
        "opens": round_.opens_at,
        "closes": round_.closes_at,
        "scheduled_release": round_.publish_at,
        "published": publication.published_at if publication else None,
    }[rule.milestone]
    if milestone is None:
        return None
    due = milestone + timedelta(minutes=rule.offset_minutes)
    return max(due, round_.opens_at) if rule.audience == "remaining" else due


def relevant(
    rule: NotificationRule | RuleInput,
    round_: Round,
    publication: Publication | None,
    now: datetime,
) -> bool:
    if round_.status in (RoundStatus.DRAFT, RoundStatus.CANCELLED, RoundStatus.UNPUBLISHING):
        return False
    if publication and (
        publication.is_imported or publication.state == PublicationState.UNPUBLISHED
    ):
        return False
    if rule.milestone == "published":
        return bool(
            publication
            and publication.state == PublicationState.PUBLISHED
            and round_.status == RoundStatus.PUBLISHED
        )
    if rule.milestone == "opens":
        return now < (round_.opens_at if rule.offset_minutes < 0 else round_.closes_at)
    if rule.milestone == "closes" and rule.offset_minutes < 0:
        return now < round_.closes_at
    if rule.milestone == "scheduled_release":
        return not (publication and publication.published_at)
    return True


def render_message(
    rule: NotificationRule | RuleInput, series: Series, round_: Round, settings: Settings
) -> str:
    def local(value: datetime) -> str:
        return value.astimezone(ZoneInfo(series.timezone)).strftime("%b %d, %Y at %I:%M %p %Z")

    return rule.message_template.format(
        series_name=series.name,
        round_title=round_.title,
        round_url=f"{str(settings.app_base_url).rstrip('/')}/rounds/{round_.id}",
        opens_at=local(round_.opens_at),
        closes_at=local(round_.closes_at),
        publishes_at=local(round_.publish_at),
    )


def channel_ready(series: Series, channel: str, settings: Settings) -> bool:
    return (
        settings.smtp_is_configured
        if channel == "email"
        else bool(
            series.mattermost_webhook_ciphertext
            or (series.use_shared_mattermost and settings.mattermost_is_configured)
        )
    )


def recipients(db: Session, rule: NotificationRule | RuleInput, round_: Round) -> list[User]:
    if rule.audience == "remaining":
        return [user for user in reminder_recipients(db, round_) if user.is_active]
    preference = (
        User.notify_round_published_emails
        if rule.milestone == "published"
        else User.notify_reminder_emails
    )
    return list(
        db.scalars(
            select(User)
            .join(RoundMember, RoundMember.user_id == User.id)
            .where(
                RoundMember.round_id == round_.id,
                RoundMember.removed_at.is_(None),
                User.is_active.is_(True),
                User.email.is_not(None),
                preference.is_(True),
            )
        )
    )


def collect_due(db: Session, now: datetime | None = None) -> list[uuid.UUID]:
    instant = now or datetime.now(UTC)
    settings = get_settings()
    # Lock rules in a stable order so simultaneous reconciliation cannot create
    # the same event. No network I/O happens inside this transaction.
    rules = list(
        db.scalars(
            select(NotificationRule)
            .join(Series)
            .where(
                NotificationRule.enabled.is_(True),
                NotificationRule.is_deleted.is_(False),
                Series.is_archived.is_(False),
            )
            .order_by(NotificationRule.id)
            .with_for_update(of=NotificationRule, skip_locked=True)
        )
    )
    for rule in rules:
        series = db.get(Series, rule.series_id)
        assert series is not None
        rounds = db.execute(
            select(Round, Publication)
            .outerjoin(Publication, Publication.round_id == Round.id)
            .where(
                Round.series_id == rule.series_id,
                Round.status.not_in([RoundStatus.DRAFT, RoundStatus.CANCELLED]),
                or_(
                    Round.publish_at >= rule.active_since - timedelta(days=31),
                    Publication.published_at >= rule.active_since - timedelta(days=31),
                ),
            )
        )
        for round_, publication in rounds:
            due = scheduled_at(rule, round_, publication)
            if due is None or due < rule.active_since or due > instant:
                continue
            if db.scalar(
                select(NotificationEvent.id).where(
                    NotificationEvent.rule_id == rule.id, NotificationEvent.round_id == round_.id
                )
            ):
                continue
            if not relevant(rule, round_, publication, instant):
                continue
            # A closing reminder must never invite submissions before opening.
            if rule.audience == "remaining" and instant < round_.opens_at:
                continue
            event = NotificationEvent(
                rule_id=rule.id,
                round_id=round_.id,
                scheduled_at=due,
                rule_name=rule.name,
                channel=rule.channel,
            )
            db.add(event)
            db.flush()
            if not channel_ready(series, rule.channel, settings):
                event.skip_reason = "Channel was not configured when this notification was due."
                continue
            targets: list[User | None] = []
            if rule.channel == "email":
                targets.extend(recipients(db, rule, round_))
            else:
                targets.append(None)
            if not targets:
                event.skip_reason = "No eligible members."
            for user in targets:
                db.add(
                    NotificationDelivery(
                        event_id=event.id,
                        recipient_key=str(user.id) if user else "mattermost",
                        user_id=user.id if user else None,
                        next_attempt_at=instant,
                    )
                )
    db.flush()
    # Recalculate pending work too: moving a round earlier must not leave a
    # notification asleep until its old date. Retries retain their backoff.
    for delivery, event, rule, round_, publication in db.execute(
        select(NotificationDelivery, NotificationEvent, NotificationRule, Round, Publication)
        .join(NotificationEvent, NotificationEvent.id == NotificationDelivery.event_id)
        .join(NotificationRule, NotificationRule.id == NotificationEvent.rule_id)
        .join(Round, Round.id == NotificationEvent.round_id)
        .outerjoin(Publication, Publication.round_id == Round.id)
        .where(NotificationDelivery.status.in_(["pending", "retry"]))
        .with_for_update(of=NotificationDelivery, skip_locked=True)
    ):
        due = scheduled_at(rule, round_, publication)
        if delivery.status == "pending":
            delivery.next_attempt_at = max(due, instant) if due else instant
        if not rule.enabled or rule.is_deleted:
            delivery.next_attempt_at = instant
        if due:
            event.scheduled_at = due
    db.flush()
    return list(
        db.scalars(
            select(NotificationDelivery.id)
            .where(
                NotificationDelivery.status.in_(["pending", "retry"]),
                NotificationDelivery.next_attempt_at <= instant,
            )
            .order_by(NotificationDelivery.next_attempt_at)
            .limit(500)
        )
    )


def deliver(db: Session, delivery_id: uuid.UUID, now: datetime | None = None) -> None:
    instant = now or datetime.now(UTC)
    delivery = db.scalar(
        select(NotificationDelivery)
        .where(NotificationDelivery.id == delivery_id)
        .with_for_update(skip_locked=True)
    )
    if delivery is None or delivery.status not in ("pending", "retry"):
        return
    if delivery.next_attempt_at > instant:
        return
    event = db.get(NotificationEvent, delivery.event_id)
    assert event is not None
    rule = db.get(NotificationRule, event.rule_id)
    round_ = db.get(Round, event.round_id)
    assert rule is not None and round_ is not None
    series = db.get(Series, rule.series_id)
    assert series is not None
    publication = db.scalar(select(Publication).where(Publication.round_id == round_.id))
    due = scheduled_at(rule, round_, publication)
    settings = get_settings()
    reason = None
    if not rule.enabled or rule.is_deleted or series.is_archived:
        reason = "Rule or series is disabled."
    elif rule.channel != event.channel:
        reason = "Delivery channel changed."
    elif due is None or due < rule.active_since or not relevant(rule, round_, publication, instant):
        reason = "This notification is no longer applicable."
    elif not channel_ready(series, rule.channel, settings):
        reason = "Channel is not configured."
    elif due > instant:
        delivery.next_attempt_at = due
        event.scheduled_at = due
        db.commit()
        return
    user = None
    if not reason and rule.channel == "email":
        user = next(
            (
                candidate
                for candidate in recipients(db, rule, round_)
                if candidate.id == delivery.user_id
            ),
            None,
        )
        if user is None:
            reason = "Member is no longer eligible or has opted out."
    if reason:
        delivery.status = "skipped"
        delivery.last_error = reason
        db.commit()
        return
    delivery.attempt_count += 1
    delivery.message = render_message(rule, series, round_, settings)
    try:
        if rule.channel == "email":
            assert user is not None and user.email is not None
            subject = " ".join(f"{series.name}: {rule.name} — {round_.title}".splitlines())
            body = (
                delivery.message
                + "\n\nManage your email preferences: "
                + str(settings.app_base_url).rstrip("/")
                + "/settings"
            )
            email.send_email(settings, user.email, subject, body)
        else:
            webhook = (
                decrypt(
                    series.mattermost_webhook_ciphertext,
                    settings.credential_encryption_key.get_secret_value(),
                )
                if series.mattermost_webhook_ciphertext
                else None
            )
            mattermost.post_message(settings, delivery.message, webhook_url=webhook)
    except (email.EmailError, mattermost.MattermostError, InvalidToken):
        # Provider exceptions may contain recipient addresses or webhook tokens.
        delivery.last_error = "Delivery failed. Check the channel configuration."
        delivery.status = "failed" if delivery.attempt_count >= MAX_ATTEMPTS else "retry"
        delivery.next_attempt_at = instant + timedelta(minutes=2**delivery.attempt_count)
    else:
        delivery.status = "sent"
        delivery.sent_at = instant
        delivery.last_error = None
    db.commit()
