"""Integration coverage for contributor-scoped series history."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from app.api.routes.rounds import get_round, list_round_submissions
from app.api.routes.series import get_series_history, list_my_series
from app.db.models import (
    ContributorGroup,
    ContributorGroupMember,
    PlatformRole,
    Round,
    RoundMember,
    RoundStatus,
    Series,
    Submission,
    SubmissionStatus,
    Track,
    User,
)
from app.db.session import get_session_factory


def test_series_history_does_not_leak_another_group_round() -> None:
    suffix = uuid.uuid4().hex[:12]
    now = datetime.now(UTC)
    with get_session_factory()() as db:
        member_one = User(
            oidc_issuer="https://issuer.test",
            oidc_subject=f"series-member-one-{suffix}",
            platform_role=PlatformRole.MEMBER,
        )
        member_two = User(
            oidc_issuer="https://issuer.test",
            oidc_subject=f"series-member-two-{suffix}",
            platform_role=PlatformRole.MEMBER,
        )
        outsider = User(
            oidc_issuer="https://issuer.test",
            oidc_subject=f"series-outsider-{suffix}",
            platform_role=PlatformRole.MEMBER,
        )
        administrator = User(
            oidc_issuer="https://issuer.test",
            oidc_subject=f"series-admin-{suffix}",
            platform_role=PlatformRole.ADMIN,
        )
        series = Series(
            name=f"Private groups {suffix}",
            slug=f"private-groups-{suffix}",
            timezone="UTC",
            default_policies=[],
        )
        db.add_all((member_one, member_two, outsider, administrator, series))
        db.flush()
        one = Round(
            series_id=series.id,
            title="First group round",
            timezone="UTC",
            submission_limit=1,
            opens_at=now - timedelta(days=2),
            closes_at=now - timedelta(days=1),
            publish_at=now,
            status=RoundStatus.CLOSED,
            policy_snapshot=[],
        )
        two = Round(
            series_id=series.id,
            title="Second group round",
            timezone="UTC",
            submission_limit=1,
            opens_at=now - timedelta(days=2),
            closes_at=now - timedelta(days=1),
            publish_at=now,
            status=RoundStatus.CLOSED,
            policy_snapshot=[],
        )
        db.add_all((one, two))
        db.flush()
        db.add_all(
            (
                RoundMember(round_id=one.id, user_id=member_one.id),
                RoundMember(round_id=two.id, user_id=member_two.id),
            )
        )
        db.commit()

        visible_to_one = get_series_history(series.id, db, member_one)
        assert [round_["id"] for round_ in visible_to_one["rounds"]] == [str(one.id)]
        visible_to_admin = get_series_history(series.id, db, administrator)
        assert {round_["id"] for round_ in visible_to_admin["rounds"]} == {
            str(one.id),
            str(two.id),
        }
        admin_round = get_round(one.id, db, administrator)
        assert admin_round["id"] == str(one.id)
        assert list_round_submissions(one.id, db, administrator) == []
        with pytest.raises(HTTPException, match="series access required") as error:
            get_series_history(series.id, db, outsider)
        assert error.value.status_code == 403


def test_series_membership_makes_an_unscheduled_series_visible() -> None:
    suffix = uuid.uuid4().hex[:12]
    with get_session_factory()() as db:
        member = User(
            oidc_issuer="https://issuer.test",
            oidc_subject=f"future-series-member-{suffix}",
            platform_role=PlatformRole.MEMBER,
        )
        series = Series(
            name=f"Future series {suffix}",
            slug=f"future-series-{suffix}",
            timezone="UTC",
            default_policies=[],
        )
        db.add_all((member, series))
        db.flush()
        group = ContributorGroup(series_id=series.id, name="Series members")
        db.add(group)
        db.flush()
        db.add(ContributorGroupMember(group_id=group.id, user_id=member.id))
        db.commit()

        items = list_my_series(db, member)
        history = get_series_history(series.id, db, member)

        assert items == [
            {
                "id": str(series.id),
                "name": series.name,
                "description": None,
                "timezone": "UTC",
                "isAdmin": False,
                "featuredRound": None,
            }
        ]
        assert history["rounds"] == []


def test_round_submissions_fall_back_to_email_for_unnamed_contributors() -> None:
    suffix = uuid.uuid4().hex[:12]
    now = datetime.now(UTC)
    with get_session_factory()() as db:
        contributor = User(
            oidc_issuer="https://issuer.test",
            oidc_subject=f"unnamed-{suffix}",
            email=f"listener-{suffix}@example.test",
            platform_role=PlatformRole.MEMBER,
        )
        series = Series(
            name=f"Names {suffix}",
            slug=f"names-{suffix}",
            timezone="UTC",
            default_policies=[],
        )
        db.add_all((contributor, series))
        db.flush()
        round_ = Round(
            series_id=series.id,
            title="Named by email",
            timezone="UTC",
            submission_limit=1,
            opens_at=now - timedelta(days=2),
            closes_at=now - timedelta(days=1),
            publish_at=now,
            status=RoundStatus.PUBLISHED,
            policy_snapshot=[],
        )
        track = Track(
            spotify_track_id=f"email-track-{suffix}",
            name="Track",
            artist="Artist",
        )
        db.add_all((round_, track))
        db.flush()
        db.add_all(
            (
                RoundMember(round_id=round_.id, user_id=contributor.id),
                Submission(
                    round_id=round_.id,
                    contributor_id=contributor.id,
                    track_id=track.id,
                    status=SubmissionStatus.ACCEPTED,
                ),
            )
        )
        db.commit()

        entries = list_round_submissions(round_.id, db, contributor)

        assert entries[0]["contributor"]["displayName"] == contributor.email
