"""Idempotent round timeline transitions and rolling successor creation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Round, RoundMember, RoundStatus, Series


def reconcile_rounds(db: Session, now: datetime | None = None) -> int:
    """Move due scheduled/open rounds forward; safe to call repeatedly from workers."""
    instant = now or datetime.now(UTC)
    changed = 0
    for round_ in db.scalars(
        select(Round)
        .where(Round.status == RoundStatus.SCHEDULED, Round.opens_at <= instant)
        .with_for_update(skip_locked=True)
    ):
        if instant < round_.closes_at:
            round_.status = RoundStatus.OPEN
        else:
            round_.status = RoundStatus.CLOSED
        changed += 1
    for round_ in db.scalars(
        select(Round)
        .where(Round.status == RoundStatus.OPEN, Round.closes_at <= instant)
        .with_for_update(skip_locked=True)
    ):
        round_.status = RoundStatus.CLOSED
        changed += 1
    return changed


def create_rolling_successor(
    db: Session, published_round: Round, now: datetime | None = None
) -> Round | None:
    """Create one successor from a validated rolling plan after a successful publish."""
    series = db.get(Series, published_round.series_id)
    if series is None or not series.auto_start_next_round or not series.round_plan:
        return None
    plan = series.round_plan
    if plan.get("kind") != "rolling":
        return None
    duration_hours = _positive_int(plan, "duration_hours")
    publish_delay_minutes = _nonnegative_int(plan, "publish_delay_minutes", 0)
    if duration_hours is None:
        return None
    existing = db.scalar(
        select(Round).where(
            Round.series_id == series.id,
            Round.title == _successor_title(plan, published_round.title),
        )
    )
    if existing is not None:
        return existing
    opens_at = now or datetime.now(UTC)
    closes_at = opens_at + timedelta(hours=duration_hours)
    configured_limit = _nonnegative_int_or_none(plan, "submission_limit")
    successor = Round(
        series_id=series.id,
        title=_successor_title(plan, published_round.title),
        timezone=published_round.timezone,
        submission_limit=configured_limit
        if configured_limit is not None
        else published_round.submission_limit,
        opens_at=opens_at,
        closes_at=closes_at,
        publish_at=closes_at + timedelta(minutes=publish_delay_minutes),
        status=RoundStatus.OPEN,
        policy_snapshot=published_round.policy_snapshot,
    )
    db.add(successor)
    db.flush()
    members = list(
        db.scalars(
            select(RoundMember).where(
                RoundMember.round_id == published_round.id,
                RoundMember.removed_at.is_(None),
            )
        )
    )
    db.add_all(
        RoundMember(
            round_id=successor.id,
            user_id=member.user_id,
            submission_limit_override=member.submission_limit_override,
        )
        for member in members
    )
    return successor


def _successor_title(plan: dict[str, Any], previous_title: str) -> str:
    template = plan.get("title_template", "{previous_title} — next")
    return str(template).replace("{previous_title}", previous_title)[:200]


def _positive_int(plan: dict[str, Any], key: str) -> int | None:
    value = plan.get(key)
    return value if isinstance(value, int) and value > 0 else None


def _nonnegative_int(plan: dict[str, Any], key: str, default: int) -> int:
    value = plan.get(key)
    return value if isinstance(value, int) and value >= 0 else default


def _nonnegative_int_or_none(plan: dict[str, Any], key: str) -> int | None:
    value = plan.get(key)
    return value if isinstance(value, int) and value >= 0 else None
