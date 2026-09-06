"""PostgreSQL-backed tests for automatic rolling successor plans."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.db.models import PlatformRole, Round, RoundMember, RoundStatus, Series, User
from app.db.session import get_session_factory
from app.services.lifecycle import create_calendar_successor, create_rolling_successor


def test_published_rolling_round_creates_one_open_successor_with_member_snapshot() -> None:
    suffix = uuid.uuid4().hex[:12]
    published_at = datetime.now(UTC)
    with get_session_factory()() as db:
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
                "duration_hours": 72,
                "publish_delay_minutes": 30,
                "submission_limit": 3,
                "title_template": "Next after {previous_title}",
            },
        )
        db.add_all((first, second, series))
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


def test_calendar_successor_skips_elapsed_windows_and_keeps_the_series_timezone() -> None:
    suffix = uuid.uuid4().hex[:12]
    timezone = ZoneInfo("America/New_York")
    published_at = datetime(2026, 5, 10, 12, tzinfo=UTC)
    with get_session_factory()() as db:
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
