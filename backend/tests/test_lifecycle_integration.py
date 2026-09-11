"""PostgreSQL-backed tests for automatic rolling successor plans."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ExternalAccount,
    ExternalProvider,
    PlatformRole,
    Round,
    RoundMember,
    RoundStatus,
    Series,
    User,
)
from app.services.lifecycle import (
    create_calendar_successor,
    create_rolling_successor,
    create_successor,
    reconcile_round_status,
    reconcile_rounds,
    start_due_open_announcements,
    status_for_timeline,
)


def test_status_for_timeline_opens_a_round_that_is_currently_in_its_window(db: Session) -> None:
    now = datetime.now(UTC)

    assert (
        status_for_timeline(now - timedelta(minutes=1), now + timedelta(minutes=1), now)
        is RoundStatus.OPEN
    )


def test_reconcile_rounds_reports_only_the_rounds_that_just_opened(db: Session) -> None:
    suffix = uuid.uuid4().hex[:12]
    now = datetime.now(UTC)
    series = Series(
        name=f"Reconcile {suffix}",
        slug=f"reconcile-{suffix}",
        timezone="UTC",
        default_policies=[],
    )
    db.add(series)
    db.flush()
    opening = Round(
        series_id=series.id,
        title="Opening now",
        timezone="UTC",
        submission_limit=1,
        opens_at=now - timedelta(minutes=1),
        closes_at=now + timedelta(days=1),
        publish_at=now + timedelta(days=2),
        status=RoundStatus.SCHEDULED,
        policy_snapshot=[],
    )
    already_open = Round(
        series_id=series.id,
        title="Already open",
        timezone="UTC",
        submission_limit=1,
        opens_at=now - timedelta(days=1),
        closes_at=now + timedelta(days=1),
        publish_at=now + timedelta(days=2),
        status=RoundStatus.OPEN,
        policy_snapshot=[],
    )
    skips_straight_to_closed = Round(
        series_id=series.id,
        title="Opens and closes before we notice",
        timezone="UTC",
        submission_limit=1,
        opens_at=now - timedelta(days=2),
        closes_at=now - timedelta(days=1),
        publish_at=now,
        status=RoundStatus.SCHEDULED,
        policy_snapshot=[],
    )
    already_open.opened_announced_at = now - timedelta(days=1)
    db.add_all((opening, already_open, skips_straight_to_closed))
    db.commit()

    reconcile_rounds(db, now=now)
    opened = start_due_open_announcements(db, now=now)

    assert opened == [opening.id]
    db.commit()
    assert db.get(Round, skips_straight_to_closed.id).status is RoundStatus.CLOSED  # type: ignore[union-attr]
    reconcile_rounds(db, now=now + timedelta(minutes=1))
    assert start_due_open_announcements(db, now=now + timedelta(minutes=1)) == []


def test_rounds_opened_outside_the_worker_are_still_announced_once(
    db: Session,
    make_user: Callable[..., User],
    make_series: Callable[..., Series],
    make_round: Callable[..., Round],
) -> None:
    """A page load that reconciles a round, or an auto-created successor, must announce too."""
    now = datetime.now(UTC)
    series = make_series()
    reconciled_by_a_page_load = make_round(
        series,
        status=RoundStatus.SCHEDULED,
        opens_at=now - timedelta(minutes=1),
        closes_at=now + timedelta(days=1),
    )
    db.commit()
    assert reconcile_round_status(reconciled_by_a_page_load, now=now)
    db.commit()

    plan_series = make_series(
        auto_start=True,
        round_plan={"kind": "rolling", "duration_days": 7},
    )
    published = make_round(
        plan_series,
        status=RoundStatus.PUBLISHED,
        opens_at=now - timedelta(days=14),
        closes_at=now - timedelta(days=7),
        members=[make_user(name="Member")],
    )
    successor = create_successor(db, published, now=now)
    assert successor is not None and successor.status is RoundStatus.OPEN
    db.commit()

    claimed = start_due_open_announcements(db, now=now)

    assert sorted(claimed) == sorted([reconciled_by_a_page_load.id, successor.id])
    db.commit()
    assert start_due_open_announcements(db, now=now + timedelta(minutes=1)) == []


def test_published_rolling_round_creates_one_open_successor_with_member_snapshot(
    db: Session,
) -> None:
    suffix = uuid.uuid4().hex[:12]
    published_at = datetime.now(UTC)
    first = User(
        oidc_issuer="https://issuer.test",
        oidc_subject=f"first-{suffix}",
        platform_role=PlatformRole.MEMBER,
    )
    second = User(
        oidc_issuer="https://issuer.test",
        oidc_subject=f"second-{suffix}",
        platform_role=PlatformRole.MEMBER,
    )
    series = Series(
        name=f"Rolling series {suffix}",
        slug=f"rolling-{suffix}",
        timezone="UTC",
        default_policies=[],
        auto_start_next_round=True,
        round_plan={
            "kind": "rolling",
            "duration_days": 3,
            "publish_delay_minutes": 30,
            "submission_limit": 3,
            "title_template": "Next after {previous_title}",
        },
    )
    db.add_all((first, second, series))
    db.flush()
    publisher = ExternalAccount(
        user_id=first.id,
        provider=ExternalProvider.SPOTIFY,
        provider_subject=f"rolling-publisher-{suffix}",
    )
    db.add(publisher)
    db.flush()
    published = Round(
        series_id=series.id,
        title=f"Published {suffix}",
        timezone="UTC",
        submission_limit=1,
        opens_at=published_at - timedelta(days=4),
        closes_at=published_at - timedelta(days=1),
        publish_at=published_at - timedelta(hours=1),
        status=RoundStatus.PUBLISHED,
        published_sequence=1,
        publisher_account_id=publisher.id,
        policy_snapshot=[{"kind": "no_duplicate_in_round"}],
    )
    db.add(published)
    db.flush()
    db.add_all(
        (
            RoundMember(round_id=published.id, user_id=first.id),
            RoundMember(round_id=published.id, user_id=second.id, submission_limit_override=2),
        )
    )
    db.commit()

    successor = create_rolling_successor(db, published, now=published_at)
    assert successor is not None
    db.commit()
    assert successor.status is RoundStatus.OPEN
    assert successor.title == f"Next after {published.title}"
    assert successor.opens_at == published_at
    assert successor.closes_at == published_at + timedelta(hours=72)
    assert successor.publish_at == published_at + timedelta(hours=72, minutes=30)
    assert successor.submission_limit == 3
    assert successor.policy_snapshot == published.policy_snapshot
    assert successor.publisher_account_id == publisher.id
    assert successor.successor_of_round_id == published.id
    members = list(
        db.scalars(
            select(RoundMember)
            .where(RoundMember.round_id == successor.id)
            .order_by(RoundMember.user_id)
        )
    )
    assert len(members) == 2
    assert {member.submission_limit_override for member in members} == {None, 2}

    assert create_rolling_successor(db, published, now=published_at) is successor


def test_successor_identity_does_not_confuse_a_manually_scheduled_matching_title(
    db: Session,
) -> None:
    suffix = uuid.uuid4().hex[:12]
    now = datetime.now(UTC)
    series = Series(
        name=f"Identity {suffix}",
        slug=f"identity-{suffix}",
        timezone="UTC",
        default_policies=[],
        auto_start_next_round=True,
        round_plan={"kind": "rolling", "duration_hours": 24},
    )
    db.add(series)
    db.flush()
    published = Round(
        series_id=series.id,
        title="September",
        timezone="UTC",
        submission_limit=1,
        opens_at=now - timedelta(days=3),
        closes_at=now - timedelta(days=2),
        publish_at=now - timedelta(days=1),
        status=RoundStatus.PUBLISHED,
        policy_snapshot=[],
    )
    manual = Round(
        series_id=series.id,
        title="September — next",
        timezone="UTC",
        submission_limit=8,
        opens_at=now + timedelta(days=5),
        closes_at=now + timedelta(days=6),
        publish_at=now + timedelta(days=7),
        status=RoundStatus.SCHEDULED,
        policy_snapshot=[],
    )
    db.add_all((published, manual))
    db.commit()

    successor = create_rolling_successor(db, published, now=now)

    assert successor is not None
    assert successor.id != manual.id
    assert successor.successor_of_round_id == published.id
    assert successor.submission_limit == 1


def test_calendar_successor_skips_elapsed_windows_and_keeps_the_series_timezone(
    db: Session,
) -> None:
    suffix = uuid.uuid4().hex[:12]
    timezone = ZoneInfo("America/New_York")
    published_at = datetime(2026, 5, 10, 12, tzinfo=UTC)
    user = User(
        oidc_issuer="https://issuer.test",
        oidc_subject=f"calendar-member-{suffix}",
        platform_role=PlatformRole.MEMBER,
    )
    series = Series(
        name=f"Calendar {suffix}",
        slug=f"calendar-{suffix}",
        timezone="America/New_York",
        default_policies=[],
        auto_start_next_round=True,
        round_plan={
            "kind": "calendar",
            "open_day": 1,
            "duration_days": 7,
            "publish_delay_minutes": 90,
            "submission_limit": 2,
            "title_template": "{year}-{month:02d}",
        },
    )
    db.add_all((user, series))
    db.flush()
    publisher = ExternalAccount(
        user_id=user.id,
        provider=ExternalProvider.SPOTIFY,
        provider_subject=f"calendar-publisher-{suffix}",
    )
    db.add(publisher)
    db.flush()
    published = Round(
        series_id=series.id,
        title="2026-04",
        timezone="America/New_York",
        submission_limit=1,
        opens_at=datetime(2026, 4, 1, 9, tzinfo=timezone),
        closes_at=datetime(2026, 4, 8, 9, tzinfo=timezone),
        publish_at=datetime(2026, 4, 8, 10, 30, tzinfo=timezone),
        status=RoundStatus.PUBLISHED,
        policy_snapshot=[{"kind": "no_duplicate_in_round"}],
        publisher_account_id=publisher.id,
    )
    db.add(published)
    db.flush()
    db.add(RoundMember(round_id=published.id, user_id=user.id, submission_limit_override=1))
    db.commit()

    successor = create_calendar_successor(db, published, now=published_at)
    assert successor is not None
    assert successor.title == "2026-06"
    assert successor.status is RoundStatus.SCHEDULED
    assert successor.opens_at == datetime(2026, 6, 1, 13, tzinfo=UTC)
    assert successor.closes_at == datetime(2026, 6, 8, 13, tzinfo=UTC)
    assert successor.publish_at == datetime(2026, 6, 8, 14, 30, tzinfo=UTC)
    assert successor.submission_limit == 2
    assert successor.policy_snapshot == published.policy_snapshot
    assert successor.publisher_account_id == publisher.id
    assert successor.successor_of_round_id == published.id
    db.flush()
    assert (
        db.scalar(
            select(RoundMember.submission_limit_override).where(
                RoundMember.round_id == successor.id,
                RoundMember.user_id == user.id,
            )
        )
        == 1
    )
    assert create_calendar_successor(db, published, now=published_at) is successor


def test_full_month_successor_closes_at_month_end_and_releases_next_day(db: Session) -> None:
    suffix = uuid.uuid4().hex[:12]
    series = Series(
        name=f"Monthly {suffix}",
        slug=f"monthly-{suffix}",
        timezone="America/New_York",
        default_policies=[],
        auto_start_next_round=True,
        round_plan={
            "kind": "calendar",
            "open_day": 1,
            "duration_days": 1,
            "full_month": True,
        },
    )
    db.add(series)
    db.flush()
    timezone = ZoneInfo("America/New_York")
    published = Round(
        series_id=series.id,
        title="January",
        timezone="America/New_York",
        submission_limit=2,
        opens_at=datetime(2026, 1, 1, 9, tzinfo=timezone),
        closes_at=datetime(2026, 2, 1, 9, tzinfo=timezone),
        publish_at=datetime(2026, 2, 2, 9, tzinfo=timezone),
        status=RoundStatus.PUBLISHED,
        policy_snapshot=[],
    )
    db.add(published)
    db.commit()

    successor = create_calendar_successor(db, published, now=datetime(2026, 2, 2, 15, tzinfo=UTC))

    assert successor is not None
    assert successor.opens_at == datetime(2026, 2, 1, 14, tzinfo=UTC)
    assert successor.closes_at == datetime(2026, 3, 1, 14, tzinfo=UTC)
    assert successor.publish_at == datetime(2026, 3, 2, 14, tzinfo=UTC)
