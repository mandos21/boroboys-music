"""Integration coverage for contributor-scoped series history."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.routes.rounds import get_round, list_round_submission_counts, list_round_submissions
from app.api.routes.series import (
    _series_genre_insights,
    accept_series_invite,
    get_series_genre_insights,
    get_series_history,
    list_my_series,
)
from app.core.security import hash_secret
from app.db.models import (
    ContributorGroup,
    ContributorGroupMember,
    PlatformRole,
    Round,
    RoundMember,
    RoundStatus,
    Series,
    SeriesInvite,
    Submission,
    SubmissionStatus,
    Track,
    TrackGenre,
    User,
)


def test_series_history_does_not_leak_another_group_round(db: Session) -> None:
    suffix = uuid.uuid4().hex[:12]
    now = datetime.now(UTC)
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
    # Management access is not contributor access: the client must not offer
    # the administrator controls that require round membership.
    assert admin_round["canManage"] is True
    assert admin_round["isMember"] is False
    assert get_round(one.id, db, member_one)["isMember"] is True
    assert list_round_submissions(one.id, db, administrator) == []
    with pytest.raises(HTTPException, match="series access required") as error:
        get_series_history(series.id, db, outsider)
    assert error.value.status_code == 403


def test_series_genre_insights_does_not_leak_another_group_round(db: Session) -> None:
    """The deferred insights endpoint must mirror the history endpoint's access rules."""
    suffix = uuid.uuid4().hex[:12]
    now = datetime.now(UTC)
    member_one = User(
        oidc_issuer="https://issuer.test",
        oidc_subject=f"insights-member-one-{suffix}",
        platform_role=PlatformRole.MEMBER,
    )
    member_two = User(
        oidc_issuer="https://issuer.test",
        oidc_subject=f"insights-member-two-{suffix}",
        platform_role=PlatformRole.MEMBER,
    )
    outsider = User(
        oidc_issuer="https://issuer.test",
        oidc_subject=f"insights-outsider-{suffix}",
        platform_role=PlatformRole.MEMBER,
    )
    administrator = User(
        oidc_issuer="https://issuer.test",
        oidc_subject=f"insights-admin-{suffix}",
        platform_role=PlatformRole.ADMIN,
    )
    series = Series(
        name=f"Private insights {suffix}",
        slug=f"private-insights-{suffix}",
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
    track_one = Track(
        spotify_track_id=f"insights-track-one-{suffix}", name="Track One", artist="Artist One"
    )
    track_two = Track(
        spotify_track_id=f"insights-track-two-{suffix}", name="Track Two", artist="Artist Two"
    )
    db.add_all((track_one, track_two))
    db.flush()
    db.add_all(
        (
            Submission(
                round_id=one.id,
                contributor_id=member_one.id,
                track_id=track_one.id,
                status=SubmissionStatus.ACCEPTED,
            ),
            Submission(
                round_id=two.id,
                contributor_id=member_two.id,
                track_id=track_two.id,
                status=SubmissionStatus.ACCEPTED,
            ),
        )
    )
    db.add_all(
        (
            TrackGenre(track_id=track_one.id, genre_key="rock", name="rock"),
            TrackGenre(track_id=track_two.id, genre_key="pop", name="pop"),
        )
    )
    db.commit()

    visible_to_one = get_series_genre_insights(series.id, db, member_one)
    assert {genre["name"] for genre in visible_to_one["genreSpread"]} == {"rock"}
    visible_to_admin = get_series_genre_insights(series.id, db, administrator)
    assert {genre["name"] for genre in visible_to_admin["genreSpread"]} == {"rock", "pop"}
    with pytest.raises(HTTPException, match="series access required") as error:
        get_series_genre_insights(series.id, db, outsider)
    assert error.value.status_code == 403


def test_series_membership_makes_an_unscheduled_series_visible(db: Session) -> None:
    suffix = uuid.uuid4().hex[:12]
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
            "coverImageUrl": None,
            "accentColor": None,
            "fallbackArtworkUrl": None,
            "isAdmin": False,
            "featuredRound": None,
        }
    ]
    assert history["rounds"] == []


def test_open_series_are_listed_first_with_contributor_progress(db: Session) -> None:
    suffix = uuid.uuid4().hex[:12]
    now = datetime.now(UTC)
    listener = User(
        oidc_issuer="https://issuer.test",
        oidc_subject=f"progress-listener-{suffix}",
        platform_role=PlatformRole.MEMBER,
    )
    another_contributor = User(
        oidc_issuer="https://issuer.test",
        oidc_subject=f"progress-other-{suffix}",
        platform_role=PlatformRole.MEMBER,
    )
    open_series = Series(
        name=f"Open series {suffix}",
        slug=f"open-series-{suffix}",
        timezone="UTC",
        default_policies=[],
    )
    closed_series = Series(
        name=f"Closed series {suffix}",
        slug=f"closed-series-{suffix}",
        timezone="UTC",
        default_policies=[],
    )
    db.add_all((listener, another_contributor, open_series, closed_series))
    db.flush()
    open_round = Round(
        series_id=open_series.id,
        title="Open now",
        timezone="UTC",
        submission_limit=3,
        opens_at=now - timedelta(days=1),
        closes_at=now + timedelta(days=1),
        publish_at=now + timedelta(days=2),
        status=RoundStatus.OPEN,
        policy_snapshot=[],
    )
    closed_round = Round(
        series_id=closed_series.id,
        title="Old news",
        timezone="UTC",
        submission_limit=3,
        opens_at=now - timedelta(days=3),
        closes_at=now - timedelta(days=2),
        publish_at=now - timedelta(days=1),
        status=RoundStatus.PUBLISHED,
        policy_snapshot=[],
    )
    track = Track(spotify_track_id=f"progress-track-{suffix}", name="Track", artist="Artist")
    db.add_all((open_round, closed_round, track))
    db.flush()
    db.add_all(
        (
            RoundMember(round_id=open_round.id, user_id=listener.id),
            RoundMember(round_id=open_round.id, user_id=another_contributor.id),
            RoundMember(round_id=closed_round.id, user_id=listener.id),
            Submission(
                round_id=open_round.id,
                contributor_id=another_contributor.id,
                track_id=track.id,
                status=SubmissionStatus.ACCEPTED,
            ),
        )
    )
    db.commit()

    items = list_my_series(db, listener)

    assert [item["id"] for item in items] == [str(open_series.id), str(closed_series.id)]
    assert items[0]["featuredRound"] == {
        "id": str(open_round.id),
        "title": "Open now",
        "status": "open",
        "opensAt": open_round.opens_at.isoformat(),
        "closesAt": open_round.closes_at.isoformat(),
        "publishAt": open_round.publish_at.isoformat(),
        "submittedCount": 1,
        "contributorCount": 2,
        "prompt": None,
    }


def test_round_submissions_fall_back_to_the_address_local_part_for_unnamed_contributors(
    db: Session,
) -> None:
    suffix = uuid.uuid4().hex[:12]
    now = datetime.now(UTC)
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

    # Identifies the person to their friends without publishing their address.
    assert entries[0]["contributor"]["displayName"] == f"listener-{suffix}"


def test_open_round_hides_other_contributors_submissions_until_it_closes(db: Session) -> None:
    suffix = uuid.uuid4().hex[:12]
    now = datetime.now(UTC)
    contributor_one = User(
        oidc_issuer="https://issuer.test",
        oidc_subject=f"secret-one-{suffix}",
        display_name="Contributor One",
        platform_role=PlatformRole.MEMBER,
    )
    contributor_two = User(
        oidc_issuer="https://issuer.test",
        oidc_subject=f"secret-two-{suffix}",
        display_name="Contributor Two",
        platform_role=PlatformRole.MEMBER,
    )
    series = Series(
        name=f"Secret round {suffix}",
        slug=f"secret-round-{suffix}",
        timezone="UTC",
        default_policies=[],
    )
    db.add_all((contributor_one, contributor_two, series))
    db.flush()
    round_ = Round(
        series_id=series.id,
        title="Still open",
        timezone="UTC",
        submission_limit=2,
        opens_at=now - timedelta(days=1),
        closes_at=now + timedelta(days=1),
        publish_at=now + timedelta(days=2),
        status=RoundStatus.OPEN,
        policy_snapshot=[],
    )
    track_one = Track(
        spotify_track_id=f"secret-track-one-{suffix}",
        name="Song One",
        artist="A",
        artwork_url="https://example.test/one.jpg",
    )
    track_two = Track(
        spotify_track_id=f"secret-track-two-{suffix}",
        name="Song Two",
        artist="B",
        artwork_url="https://example.test/two.jpg",
    )
    db.add_all((round_, track_one, track_two))
    db.flush()
    db.add_all(
        (
            RoundMember(round_id=round_.id, user_id=contributor_one.id),
            RoundMember(round_id=round_.id, user_id=contributor_two.id),
            Submission(
                round_id=round_.id,
                contributor_id=contributor_one.id,
                track_id=track_one.id,
                status=SubmissionStatus.ACCEPTED,
            ),
            Submission(
                round_id=round_.id,
                contributor_id=contributor_two.id,
                track_id=track_two.id,
                status=SubmissionStatus.ACCEPTED,
            ),
        )
    )
    db.commit()

    # While open, each contributor sees only their own entry.
    own_view = list_round_submissions(round_.id, db, contributor_one)
    assert [entry["contributor"]["id"] for entry in own_view] == [str(contributor_one.id)]

    # The counts endpoint says how much has been shared without naming tracks.
    count_entries = list_round_submission_counts(round_.id, db, contributor_one)
    assert all("track" not in entry for entry in count_entries)
    counts = {entry["contributor"]["id"]: entry["count"] for entry in count_entries}
    assert counts == {str(contributor_one.id): 1, str(contributor_two.id): 1}

    # The round's own cover art withholds submitted album art too.
    detail = get_round(round_.id, db, contributor_one)
    assert detail["backgroundArtworkUrl"] is None
    assert detail["artworkUrls"] == []

    # Once the round closes, everyone's picks (and art) are revealed.
    round_.status = RoundStatus.CLOSED
    db.commit()
    closed_view = list_round_submissions(round_.id, db, contributor_one)
    assert {entry["contributor"]["id"] for entry in closed_view} == {
        str(contributor_one.id),
        str(contributor_two.id),
    }
    closed_detail = get_round(round_.id, db, contributor_one)
    assert closed_detail["backgroundArtworkUrl"] in {
        "https://example.test/one.jpg",
        "https://example.test/two.jpg",
    }
    assert set(closed_detail["artworkUrls"]) == {
        "https://example.test/one.jpg",
        "https://example.test/two.jpg",
    }


def test_series_stats_returns_every_cached_genre_for_the_expandable_fingerprint(
    db: Session,
) -> None:
    suffix = uuid.uuid4().hex[:12]
    now = datetime.now(UTC)
    contributor = User(
        oidc_issuer="https://issuer.test",
        oidc_subject=f"genre-fingerprint-{suffix}",
        platform_role=PlatformRole.MEMBER,
    )
    series = Series(
        name=f"Genre fingerprint {suffix}",
        slug=f"genre-fingerprint-{suffix}",
        timezone="UTC",
        default_policies=[],
    )
    db.add_all((contributor, series))
    db.flush()
    round_ = Round(
        series_id=series.id,
        title="Every cached genre",
        timezone="UTC",
        submission_limit=20,
        opens_at=now - timedelta(days=2),
        closes_at=now - timedelta(days=1),
        publish_at=now,
        status=RoundStatus.PUBLISHED,
        policy_snapshot=[],
    )
    genre_names = [
        *(f"other genre {index}" for index in range(11)),
        "garage rock",
        "rock",
        "rock",
        "pop",
    ]
    tracks = [
        Track(
            spotify_track_id=f"genre-track-{index}-{suffix}",
            name=f"Track {index}",
            artist="Artist",
        )
        for index in range(len(genre_names))
    ]
    db.add(round_)
    db.add_all(tracks)
    db.flush()
    db.add_all(
        Submission(
            round_id=round_.id,
            contributor_id=contributor.id,
            track_id=track.id,
            status=SubmissionStatus.ACCEPTED,
        )
        for track in tracks
    )
    db.add_all(
        TrackGenre(track_id=track.id, genre_key=f"genre-{index}", name=genre)
        for index, (track, genre) in enumerate(zip(tracks, genre_names, strict=True))
    )
    db.commit()

    stats = _series_genre_insights(db, [round_])

    assert len(stats["genreSpread"]) == len(set(genre_names))
    assert {genre["name"] for genre in stats["genreSpread"]} == set(genre_names)
    # Taxonomy family determines the cloud's reading order, then frequency
    # makes the most representative labels lead within that family.
    assert [genre["name"] for genre in stats["genreSpread"][:3]] == [
        "rock",
        "garage rock",
        "pop",
    ]
    contributor = stats["contributors"][0]
    assert {genre["name"] for genre in contributor["genres"]} == set(genre_names)
    # Exact tags are the one contributor-level genre representation. The client
    # derives family totals from them, so independent aggregates cannot drift.
    assert "groups" not in contributor


def test_series_invite_adds_a_member_once_and_respects_its_use_limit(db: Session) -> None:
    suffix = uuid.uuid4().hex[:12]
    owner = User(
        oidc_issuer="https://issuer.test",
        oidc_subject=f"invite-owner-{suffix}",
        platform_role=PlatformRole.MEMBER,
    )
    listener = User(
        oidc_issuer="https://issuer.test",
        oidc_subject=f"invite-listener-{suffix}",
        platform_role=PlatformRole.MEMBER,
    )
    another_listener = User(
        oidc_issuer="https://issuer.test",
        oidc_subject=f"invite-other-{suffix}",
        platform_role=PlatformRole.MEMBER,
    )
    series = Series(
        name=f"Invite series {suffix}",
        slug=f"invite-series-{suffix}",
        timezone="UTC",
        default_policies=[],
    )
    db.add_all((owner, listener, another_listener, series))
    db.flush()
    invite = SeriesInvite(
        series_id=series.id,
        created_by_id=owner.id,
        token_hash=hash_secret(f"invite-{suffix}"),
        role="contributor",
        expires_at=datetime.now(UTC) + timedelta(days=1),
        max_uses=1,
    )
    db.add(invite)
    db.commit()

    accepted = accept_series_invite(f"invite-{suffix}", db, listener)
    assert accepted == {"seriesId": str(series.id), "role": "contributor"}
    assert list_my_series(db, listener)[0]["id"] == str(series.id)
    # Returning through the same link is harmless and does not consume a
    # scarce single-use invitation a second time.
    assert accept_series_invite(f"invite-{suffix}", db, listener) == accepted

    with pytest.raises(HTTPException, match="invite is unavailable") as error:
        accept_series_invite(f"invite-{suffix}", db, another_listener)
    assert error.value.status_code == 404
