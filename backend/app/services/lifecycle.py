"""Idempotent round timeline transitions and rolling successor creation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

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


def create_successor(
    db: Session, published_round: Round, now: datetime | None = None
) -> Round | None:
    """Create one successor from the configured plan after a successful publish."""
    series = db.get(Series, published_round.series_id)
    if series is None or not series.auto_start_next_round or not series.round_plan:
        return None
    plan = series.round_plan
    if plan.get("kind") == "rolling":
        return create_rolling_successor(db, published_round, now=now, series=series)
    if plan.get("kind") == "calendar":
        return create_calendar_successor(db, published_round, now=now, series=series)
    return None


def create_rolling_successor(
    db: Session,
    published_round: Round,
    now: datetime | None = None,
    series: Series | None = None,
) -> Round | None:
    """Create one successor from a validated rolling plan after a successful publish."""
    series = series or db.get(Series, published_round.series_id)
    if series is None or not series.auto_start_next_round or not series.round_plan:
        return None
    plan = series.round_plan
    if plan.get("kind") != "rolling":
        return None
    duration_days = _positive_int(plan, "duration_days")
    duration_hours = _positive_int(plan, "duration_hours")
    publish_delay_minutes = _nonnegative_int(plan, "publish_delay_minutes", 0)
    if duration_days is None and duration_hours is None:
        return None
    existing = db.scalar(
        select(Round).where(Round.successor_of_round_id == published_round.id)
    )
    if existing is not None:
        return existing
    opens_at = now or datetime.now(UTC)
    closes_at = opens_at + (
        timedelta(days=duration_days)
        if duration_days is not None
        else timedelta(hours=duration_hours or 0)
    )
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
        successor_of_round_id=published_round.id,
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


def create_calendar_successor(
    db: Session,
    published_round: Round,
    now: datetime | None = None,
    series: Series | None = None,
) -> Round | None:
    """Create the next applicable monthly calendar window from a calendar plan.

    We never create a successor whose submission window has already elapsed. If
    publication was delayed, the calculation advances through missed windows to
    the current open window or the next scheduled one in the series timezone.
    """
    series = series or db.get(Series, published_round.series_id)
    if series is None or not series.auto_start_next_round or not series.round_plan:
        return None
    plan = series.round_plan
    if plan.get("kind") != "calendar":
        return None
    open_day = _bounded_int(plan, "open_day", minimum=1, maximum=28)
    duration_days = _positive_int(plan, "duration_days")
    if open_day is None or duration_days is None:
        return None
    instant = now or datetime.now(UTC)
    timezone = ZoneInfo(published_round.timezone)
    local_previous_open = published_round.opens_at.astimezone(timezone)
    candidate = _next_month_start(local_previous_open, open_day)
    closes_candidate = _calendar_close(candidate, duration_days, plan)
    while closes_candidate <= instant.astimezone(timezone):
        candidate = _next_month_start(candidate, open_day)
        closes_candidate = _calendar_close(candidate, duration_days, plan)
    opens_at = candidate.astimezone(UTC)
    closes_at = closes_candidate.astimezone(UTC)
    if plan.get("full_month") is True:
        # A full monthly window is intentionally released the following day,
        # rather than at the instant submissions close.
        publish_at = closes_at + timedelta(days=1)
    else:
        publish_delay_minutes = _nonnegative_int(plan, "publish_delay_minutes", 0)
        publish_at = closes_at + timedelta(minutes=publish_delay_minutes)
    title = _calendar_successor_title(plan, published_round.title, candidate)
    existing = db.scalar(
        select(Round).where(Round.successor_of_round_id == published_round.id)
    )
    if existing is not None:
        return existing
    configured_limit = _nonnegative_int_or_none(plan, "submission_limit")
    successor = Round(
        series_id=series.id,
        title=title,
        timezone=published_round.timezone,
        submission_limit=(
            configured_limit if configured_limit is not None else published_round.submission_limit
        ),
        opens_at=opens_at,
        closes_at=closes_at,
        publish_at=publish_at,
        status=RoundStatus.OPEN if opens_at <= instant < closes_at else RoundStatus.SCHEDULED,
        successor_of_round_id=published_round.id,
        policy_snapshot=published_round.policy_snapshot,
    )
    db.add(successor)
    db.flush()
    _copy_active_members(db, published_round, successor)
    return successor


def _successor_title(plan: dict[str, Any], previous_title: str) -> str:
    template = plan.get("title_template", "{previous_title} — next")
    return str(template).replace("{previous_title}", previous_title)[:200]


def _calendar_successor_title(
    plan: dict[str, Any], previous_title: str, local_open: datetime
) -> str:
    template = plan.get("title_template", "{year}-{month:02d}")
    return (
        str(template)
        .replace("{previous_title}", previous_title)
        .replace("{year}", str(local_open.year))
        .replace("{month:02d}", f"{local_open.month:02d}")
        .replace("{month}", str(local_open.month))[:200]
    )


def _next_month_start(local_datetime: datetime, open_day: int) -> datetime:
    year = local_datetime.year + (local_datetime.month == 12)
    month = 1 if local_datetime.month == 12 else local_datetime.month + 1
    return local_datetime.replace(year=year, month=month, day=open_day)


def _calendar_close(candidate: datetime, duration_days: int, plan: dict[str, Any]) -> datetime:
    """Return the local closing instant for either calendar plan flavour."""
    if plan.get("full_month") is True:
        return _next_month_start(candidate, 1)
    return candidate + timedelta(days=duration_days)


def _copy_active_members(db: Session, previous: Round, successor: Round) -> None:
    members = list(
        db.scalars(
            select(RoundMember).where(
                RoundMember.round_id == previous.id,
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


def _positive_int(plan: dict[str, Any], key: str) -> int | None:
    value = plan.get(key)
    return value if isinstance(value, int) and value > 0 else None


def _nonnegative_int(plan: dict[str, Any], key: str, default: int) -> int:
    value = plan.get(key)
    return value if isinstance(value, int) and value >= 0 else default


def _nonnegative_int_or_none(plan: dict[str, Any], key: str) -> int | None:
    value = plan.get(key)
    return value if isinstance(value, int) and value >= 0 else None


def _bounded_int(plan: dict[str, Any], key: str, minimum: int, maximum: int) -> int | None:
    value = plan.get(key)
    return value if isinstance(value, int) and minimum <= value <= maximum else None
