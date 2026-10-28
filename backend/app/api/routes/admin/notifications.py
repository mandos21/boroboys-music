"""Series-admin notification configuration, previews, and delivery history."""

from __future__ import annotations

import re
import uuid
from collections import Counter
from datetime import UTC, datetime
from typing import Annotated, Literal
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, SecretStr, model_validator
from sqlalchemy import func, select

from app.api.deps import DbSession, get_current_user
from app.api.routes.admin._common import _require_series_admin, router
from app.core.config import get_settings
from app.core.security import encrypt
from app.db.models import (
    NotificationDelivery,
    NotificationEvent,
    NotificationRule,
    Publication,
    Round,
    Series,
    User,
)
from app.services.notification_rules import (
    RuleInput,
    channel_ready,
    recipients,
    relevant,
    render_message,
    scheduled_at,
)


class RuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    enabled: bool
    channel: Literal["email", "mattermost"]
    milestone: Literal["opens", "closes", "scheduled_release", "published"]
    offset_minutes: int
    audience: Literal["members", "remaining"]
    message_template: str


class ChannelUpdate(BaseModel):
    mode: Literal["shared", "custom", "disabled"]
    webhook_url: SecretStr | None = None

    @model_validator(mode="after")
    def valid_webhook(self) -> ChannelUpdate:
        if self.webhook_url is not None:
            raw = self.webhook_url.get_secret_value().strip()
            value = urlsplit(raw)
            if (
                len(raw) > 2000
                or value.scheme != "https"
                or not value.hostname
                or value.port == 0
                or value.username
                or value.password
                or value.query
                or value.fragment
                or not re.fullmatch(r"/hooks/[a-zA-Z0-9_-]+", value.path)
            ):
                raise ValueError(
                    "Use an HTTPS Mattermost incoming webhook URL ending in /hooks/token"
                )
            self.webhook_url = SecretStr(raw)
        return self


class ChannelsResponse(BaseModel):
    emailReady: bool
    mattermostReady: bool
    mattermostMode: Literal["shared", "custom", "disabled"]
    sharedMattermostReady: bool


class UpcomingResponse(BaseModel):
    ruleId: uuid.UUID
    ruleName: str
    roundId: uuid.UUID
    roundTitle: str
    channel: str
    scheduledAt: datetime | None
    message: str
    audience: str
    channelReady: bool


class HistoryResponse(BaseModel):
    id: uuid.UUID
    ruleName: str
    roundTitle: str
    channel: str
    scheduledAt: datetime
    status: str
    sent: int
    total: int
    detail: str | None


class SeriesNotificationsResponse(BaseModel):
    channels: ChannelsResponse
    rules: list[RuleResponse]
    upcoming: list[UpcomingResponse]
    history: list[HistoryResponse]
    timezone: str


class PreviewInput(RuleInput):
    round_id: uuid.UUID


def _rule(db: DbSession, series_id: uuid.UUID, rule_id: uuid.UUID) -> NotificationRule:
    rule = db.scalar(
        select(NotificationRule)
        .where(
            NotificationRule.id == rule_id,
            NotificationRule.series_id == series_id,
            NotificationRule.is_deleted.is_(False),
        )
        .with_for_update()
    )
    if rule is None:
        raise HTTPException(404, "Notification rule not found")
    return rule


@router.get("/series/{series_id}/notifications", response_model=SeriesNotificationsResponse)
def get_notifications(
    series_id: uuid.UUID, db: DbSession, user: Annotated[User, Depends(get_current_user)]
) -> SeriesNotificationsResponse:
    series = _require_series_admin(db, user, series_id)
    settings = get_settings()
    rules = list(
        db.scalars(
            select(NotificationRule)
            .where(NotificationRule.series_id == series_id, NotificationRule.is_deleted.is_(False))
            .order_by(NotificationRule.created_at, NotificationRule.id)
        )
    )
    milestone_order = {"opens": 0, "closes": 1, "scheduled_release": 2, "published": 3}
    rules.sort(
        key=lambda rule: (
            milestone_order[rule.milestone],
            rule.offset_minutes,
            0 if rule.channel == "mattermost" else 1,
            rule.name.casefold(),
            str(rule.id),
        )
    )
    now = datetime.now(UTC)
    upcoming = []
    rounds = list(
        db.execute(
            select(Round, Publication)
            .outerjoin(Publication, Publication.round_id == Round.id)
            .where(Round.series_id == series_id)
            .order_by(Round.opens_at)
        )
    )
    events = list(
        db.scalars(
            select(NotificationEvent)
            .join(NotificationRule)
            .where(NotificationRule.series_id == series_id)
            .order_by(NotificationEvent.created_at.desc())
        )
    )
    claimed = {(event.rule_id, event.round_id) for event in events}
    for rule in rules:
        if not rule.enabled or series.is_archived:
            continue
        for round_, publication in rounds:
            if (rule.id, round_.id) in claimed:
                continue
            due = scheduled_at(rule, round_, publication)
            # Publication notifications appear as waiting until there is an actual release.
            waiting = (
                rule.milestone == "published"
                and (
                    publication is None
                    or (publication.published_at is None and not publication.is_imported)
                )
                and round_.status.value in ("scheduled", "open", "closed", "publishing", "failed")
            )
            if not waiting and (
                due is None
                or due < max(rule.active_since, now)
                or not relevant(rule, round_, publication, max(now, due))
            ):
                continue
            upcoming.append(
                UpcomingResponse(
                    ruleId=rule.id,
                    ruleName=rule.name,
                    roundId=round_.id,
                    roundTitle=round_.title,
                    channel=rule.channel,
                    scheduledAt=due,
                    message=render_message(rule, series, round_, settings),
                    audience=(
                        "Mattermost channel"
                        if rule.channel == "mattermost"
                        else f"{len(recipients(db, rule, round_))} eligible members right now"
                    ),
                    channelReady=channel_ready(series, rule.channel, settings),
                )
            )
    # A moved round can have an already-created delivery waiting for a new date.
    # Include that pending work as well as rules that have not been materialized.
    pending_event_ids = set(
        db.scalars(
            select(NotificationDelivery.event_id)
            .where(NotificationDelivery.status.in_(["pending", "retry"]))
            .join(NotificationEvent)
            .join(NotificationRule)
            .where(NotificationRule.series_id == series_id)
            .distinct()
        )
    )
    by_rule = {rule.id: rule for rule in rules}
    by_round = {round_.id: (round_, publication) for round_, publication in rounds}
    for event in events:
        pending_rule = by_rule.get(event.rule_id)
        if event.id not in pending_event_ids or pending_rule is None or not pending_rule.enabled:
            continue
        round_, publication = by_round[event.round_id]
        due = scheduled_at(pending_rule, round_, publication)
        if (
            series.is_archived
            or due is None
            or due < now
            or not relevant(pending_rule, round_, publication, now)
        ):
            continue
        upcoming.append(
            UpcomingResponse(
                ruleId=pending_rule.id,
                ruleName=pending_rule.name,
                roundId=round_.id,
                roundTitle=round_.title,
                channel=pending_rule.channel,
                scheduledAt=due,
                message=render_message(pending_rule, series, round_, settings),
                audience="Queued delivery; recipients are checked before sending",
                channelReady=channel_ready(series, pending_rule.channel, settings),
            )
        )
    upcoming.sort(key=lambda item: (item.scheduledAt is None, item.scheduledAt or now))
    history = []
    recent = events[:50]
    deliveries_by_event: dict[uuid.UUID, list[NotificationDelivery]] = {
        event.id: [] for event in recent
    }
    for delivery in db.scalars(
        select(NotificationDelivery).where(NotificationDelivery.event_id.in_(deliveries_by_event))
    ):
        deliveries_by_event[delivery.event_id].append(delivery)
    titles = {round_.id: round_.title for round_, _ in rounds}
    for event in recent:
        deliveries = deliveries_by_event[event.id]
        counts = Counter(delivery.status for delivery in deliveries)
        status = (
            "skipped"
            if not deliveries
            else "retrying"
            if counts["retry"]
            else "pending"
            if counts["pending"]
            else "failed"
            if counts["failed"] and not counts["sent"]
            else "partial"
            if counts["failed"] or (counts["sent"] and counts["skipped"])
            else "sent"
            if counts["sent"]
            else "skipped"
        )
        history.append(
            HistoryResponse(
                id=event.id,
                ruleName=event.rule_name,
                roundTitle=titles[event.round_id],
                channel=event.channel,
                scheduledAt=event.scheduled_at,
                status=status,
                sent=counts["sent"],
                total=len(deliveries),
                detail=event.skip_reason
                or next((d.last_error for d in deliveries if d.last_error), None),
            )
        )
    return SeriesNotificationsResponse(
        channels=ChannelsResponse(
            emailReady=settings.smtp_is_configured,
            mattermostReady=channel_ready(series, "mattermost", settings),
            mattermostMode=(
                "custom"
                if series.mattermost_webhook_ciphertext
                else "shared"
                if series.use_shared_mattermost
                else "disabled"
            ),
            sharedMattermostReady=settings.mattermost_is_configured,
        ),
        rules=[RuleResponse.model_validate(rule) for rule in rules],
        upcoming=upcoming[:30],
        history=history,
        timezone=series.timezone,
    )


@router.put("/series/{series_id}/notifications/channel", status_code=204)
def update_channel(
    series_id: uuid.UUID,
    payload: ChannelUpdate,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> Response:
    series = _require_series_admin(db, user, series_id)
    settings = get_settings()
    if payload.mode == "custom":
        if payload.webhook_url:
            series.mattermost_webhook_ciphertext = encrypt(
                payload.webhook_url.get_secret_value(),
                settings.credential_encryption_key.get_secret_value(),
            )
            series.mattermost_webhook_key_version = settings.credential_encryption_key_version
        elif not series.mattermost_webhook_ciphertext:
            raise HTTPException(422, "Enter a Mattermost webhook URL")
    else:
        series.mattermost_webhook_ciphertext = None
        series.mattermost_webhook_key_version = None
    series.use_shared_mattermost = payload.mode == "shared"
    db.commit()
    return Response(status_code=204)


@router.post(
    "/series/{series_id}/notifications/rules", response_model=RuleResponse, status_code=201
)
def create_rule(
    series_id: uuid.UUID,
    payload: RuleInput,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> NotificationRule:
    _require_series_admin(db, user, series_id)
    # Serialize the cap check with other rule creation for this series.
    db.execute(select(Series.id).where(Series.id == series_id).with_for_update())
    count = (
        db.scalar(
            select(func.count())
            .select_from(NotificationRule)
            .where(NotificationRule.series_id == series_id, NotificationRule.is_deleted.is_(False))
        )
        or 0
    )
    if count >= 20:
        raise HTTPException(422, "A series can have up to 20 notification rules")
    rule = NotificationRule(series_id=series_id, **payload.model_dump())
    db.add(rule)
    db.commit()
    return rule


@router.put("/series/{series_id}/notifications/rules/{rule_id}", response_model=RuleResponse)
def update_rule(
    series_id: uuid.UUID,
    rule_id: uuid.UUID,
    payload: RuleInput,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> NotificationRule:
    _require_series_admin(db, user, series_id)
    rule = _rule(db, series_id, rule_id)
    if any(
        getattr(rule, key) != getattr(payload, key)
        for key in ("enabled", "milestone", "offset_minutes", "channel", "audience")
    ):
        rule.active_since = datetime.now(UTC)
    for key, value in payload.model_dump().items():
        setattr(rule, key, value)
    db.commit()
    return rule


@router.delete("/series/{series_id}/notifications/rules/{rule_id}", status_code=204)
def delete_rule(
    series_id: uuid.UUID,
    rule_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> Response:
    _require_series_admin(db, user, series_id)
    rule = _rule(db, series_id, rule_id)
    rule.is_deleted = True
    rule.enabled = False
    db.commit()
    return Response(status_code=204)


@router.post("/series/{series_id}/notifications/preview", response_model=UpcomingResponse)
def preview_rule(
    series_id: uuid.UUID,
    payload: PreviewInput,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> UpcomingResponse:
    series = _require_series_admin(db, user, series_id)
    round_ = db.get(Round, payload.round_id)
    if round_ is None or round_.series_id != series.id:
        raise HTTPException(404, "Round not found")
    publication = db.scalar(select(Publication).where(Publication.round_id == round_.id))
    settings = get_settings()
    return UpcomingResponse(
        ruleId=uuid.UUID(int=0),
        ruleName=payload.name,
        roundId=round_.id,
        roundTitle=round_.title,
        channel=payload.channel,
        scheduledAt=scheduled_at(payload, round_, publication),
        message=render_message(payload, series, round_, settings),
        audience="Mattermost channel"
        if payload.channel == "mattermost"
        else f"{len(recipients(db, payload, round_))} eligible members right now",
        channelReady=channel_ready(series, payload.channel, settings),
    )
