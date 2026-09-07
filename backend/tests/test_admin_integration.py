"""PostgreSQL-backed administration read-side authorization coverage."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from app.api.routes.admin import (
    SeriesUpdate,
    get_round_for_administration,
    get_series_for_administration,
    list_series_for_administration,
    search_users_for_series,
    update_series,
)
from app.db.models import (
    ContributorGroup,
    ContributorGroupMember,
    PlatformRole,
    Round,
    RoundMember,
    RoundStatus,
    Series,
    SeriesAdmin,
    User,
)
from app.db.session import get_session_factory


def test_series_admin_reads_only_assigned_series_and_searches_active_users() -> None:
    suffix = uuid.uuid4().hex[:12]
    with get_session_factory()() as db:
        series_admin = User(
            oidc_issuer="https://issuer.test",
            oidc_subject=f"series-admin-{suffix}",
            display_name="Series Admin",
            platform_role=PlatformRole.MEMBER,
        )
        member = User(
            oidc_issuer="https://issuer.test",
            oidc_subject=f"member-{suffix}",
            email=f"member-{suffix}@example.test",
            display_name="Matched Member",
            platform_role=PlatformRole.MEMBER,
        )
        assigned = Series(
            name=f"Assigned {suffix}",
            slug=f"assigned-{suffix}",
            timezone="UTC",
            default_policies=[],
        )
        other = Series(
            name=f"Other {suffix}",
            slug=f"other-{suffix}",
            timezone="UTC",
            default_policies=[],
        )
        db.add_all((series_admin, member, assigned, other))
        db.flush()
        group = ContributorGroup(series_id=assigned.id, name="Contributors")
        db.add_all(
            (
                SeriesAdmin(series_id=assigned.id, user_id=series_admin.id),
                group,
            )
        )
        db.flush()
        db.add(ContributorGroupMember(group_id=group.id, user_id=member.id))
        db.commit()

        visible = list_series_for_administration(db, series_admin)
        assert [item["id"] for item in visible] == [str(assigned.id)]
        detail = get_series_for_administration(assigned.id, db, series_admin)
        assert detail["groups"] == [
            {
                "id": str(group.id),
                "name": "Contributors",
                "description": None,
                "memberCount": 1,
                "members": [
                    {
                        "id": str(member.id),
                        "displayName": "Matched Member",
                        "email": member.email,
                    }
                ],
            }
        ]
        assert search_users_for_series(assigned.id, suffix, db, series_admin) == [
            {
                "id": str(member.id),
                "displayName": "Matched Member",
                "email": member.email,
            }
        ]


def test_round_administration_exposes_member_limit_overrides_and_removals() -> None:
    suffix = uuid.uuid4().hex[:12]
    now = datetime.now(UTC)
    with get_session_factory()() as db:
        admin = User(
            oidc_issuer="https://issuer.test",
            oidc_subject=f"round-admin-{suffix}",
            platform_role=PlatformRole.MEMBER,
        )
        active = User(
            oidc_issuer="https://issuer.test",
            oidc_subject=f"round-active-{suffix}",
            display_name="Active contributor",
            platform_role=PlatformRole.MEMBER,
        )
        removed = User(
            oidc_issuer="https://issuer.test",
            oidc_subject=f"round-removed-{suffix}",
            display_name="Removed contributor",
            platform_role=PlatformRole.MEMBER,
        )
        series = Series(
            name=f"Round-admin series {suffix}",
            slug=f"round-admin-{suffix}",
            timezone="UTC",
            default_policies=[],
        )
        db.add_all((admin, active, removed, series))
        db.flush()
        round_ = Round(
            series_id=series.id,
            title=f"Round detail {suffix}",
            timezone="UTC",
            submission_limit=2,
            opens_at=now + timedelta(days=1),
            closes_at=now + timedelta(days=2),
            publish_at=now + timedelta(days=3),
            status=RoundStatus.SCHEDULED,
            policy_snapshot=[],
        )
        db.add_all((SeriesAdmin(series_id=series.id, user_id=admin.id), round_))
        db.flush()
        db.add_all(
            (
                RoundMember(
                    round_id=round_.id,
                    user_id=active.id,
                    submission_limit_override=4,
                ),
                RoundMember(
                    round_id=round_.id,
                    user_id=removed.id,
                    removed_at=now,
                ),
            )
        )
        db.commit()

        detail = get_round_for_administration(round_.id, db, admin)
        assert detail["submissionLimit"] == 2
        assert detail["seriesId"] == str(series.id)
        assert detail["members"] == [
            {
                "id": str(active.id),
                "displayName": "Active contributor",
                "email": None,
                "submissionLimitOverride": 4,
                "removedAt": None,
            },
            {
                "id": str(removed.id),
                "displayName": "Removed contributor",
                "email": None,
                "submissionLimitOverride": None,
                "removedAt": now.isoformat(),
            },
        ]


def test_series_admin_can_replace_a_future_successor_plan_without_rewriting_rounds() -> None:
    suffix = uuid.uuid4().hex[:12]
    now = datetime.now(UTC)
    with get_session_factory()() as db:
        admin = User(
            oidc_issuer="https://issuer.test",
            oidc_subject=f"plan-admin-{suffix}",
            platform_role=PlatformRole.MEMBER,
        )
        series = Series(
            name=f"Plan series {suffix}",
            slug=f"plan-series-{suffix}",
            timezone="UTC",
            default_policies=[{"kind": "no_duplicate_in_round"}],
            round_plan={"kind": "rolling", "duration_hours": 72},
            auto_start_next_round=True,
        )
        db.add_all((admin, series))
        db.flush()
        round_ = Round(
            series_id=series.id,
            title="Existing snapshot",
            timezone="UTC",
            submission_limit=1,
            opens_at=now,
            closes_at=now + timedelta(days=1),
            publish_at=now + timedelta(days=1),
            status=RoundStatus.SCHEDULED,
            policy_snapshot=[{"kind": "no_duplicate_in_round"}],
        )
        db.add_all((SeriesAdmin(series_id=series.id, user_id=admin.id), round_))
        db.commit()

        result = update_series(
            series.id,
            SeriesUpdate(
                timezone="America/New_York",
                round_plan={
                    "kind": "calendar",
                    "open_day": 1,
                    "duration_days": 7,
                    "title_template": "{year}-{month:02d}",
                },
                auto_start_next_round=False,
            ),
            db,
            admin,
        )
        assert result["timezone"] == "America/New_York"
        assert result["autoStartNextRound"] is False
        assert result["roundPlan"] == {
            "kind": "calendar",
                "open_day": 1,
                "duration_days": 7,
                "full_month": False,
                "publish_delay_minutes": 0,
            "submission_limit": None,
            "title_template": "{year}-{month:02d}",
        }
        db.expire_all()
        existing = db.get(Round, round_.id)
        assert existing is not None
        assert existing.timezone == "UTC"
        assert existing.policy_snapshot == [{"kind": "no_duplicate_in_round"}]
