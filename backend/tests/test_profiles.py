"""Profile history is useful only when it respects the existing round boundary."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.profiles import get_my_profile, get_profile
from app.db.models import (
    PlatformRole,
    Round,
    RoundMember,
    Series,
    SeriesAdmin,
    Submission,
    SubmissionStatus,
    Track,
    TrackArtist,
    TrackGenre,
    User,
)


def test_profile_summarizes_shared_history_without_leaking_private_rounds(
    db: Session,
    make_round: Callable[..., Round],
    make_series: Callable[..., Series],
    make_track: Callable[..., Track],
    make_user: Callable[..., User],
) -> None:
    listener = make_user(name="Listener")
    contributor = make_user(name="Contributor")
    series = make_series()
    shared_round = make_round(series, members=[listener, contributor])
    private_round = make_round(series, members=[contributor])
    shared_track = make_track(
        name="Shared song",
        artist="Shared artist",
        album="Shared album",
        provider_metadata={"genres": ["indie rock", "dream pop"]},
    )
    private_track = make_track(
        name="Private song",
        artist="Private artist",
        album="Private album",
        provider_metadata={"genres": ["ambient"]},
    )
    db.add_all(
        (
            TrackArtist(
                track_id=shared_track.id,
                spotify_artist_id="shared-artist",
                name="Shared artist",
                position=0,
            ),
            TrackGenre(track_id=shared_track.id, genre_key="indie rock", name="indie rock"),
            TrackGenre(track_id=shared_track.id, genre_key="dream pop", name="dream pop"),
            TrackArtist(
                track_id=private_track.id,
                spotify_artist_id="private-artist",
                name="Private artist",
                position=0,
            ),
            TrackGenre(track_id=private_track.id, genre_key="ambient", name="ambient"),
        )
    )
    db.add_all(
        (
            Submission(
                round_id=shared_round.id,
                contributor_id=contributor.id,
                track_id=shared_track.id,
                status=SubmissionStatus.ACCEPTED,
            ),
            Submission(
                round_id=private_round.id,
                contributor_id=contributor.id,
                track_id=private_track.id,
                status=SubmissionStatus.ACCEPTED,
            ),
        )
    )
    db.commit()

    visible = get_profile(contributor.id, db, listener)

    assert visible["displayName"] == "Contributor"
    assert visible["stats"]["submissionCount"] == 1
    assert visible["stats"]["uniqueArtistCount"] == 1
    # Each genre carries the family group it belongs to, so the client colours
    # related genres alike rather than by their position in the list. Both of
    # these group as rock: the taxonomy places dream pop there, which naive
    # matching on the trailing word would have called pop.
    assert visible["stats"]["genreSpread"] == [
        {"name": "dream pop", "count": 1, "group": "rock"},
        {"name": "indie rock", "count": 1, "group": "rock"},
    ]
    assert [item["track"]["name"] for item in visible["submissions"]] == ["Shared song"]

    mine = get_my_profile(db, contributor)
    assert mine["stats"]["submissionCount"] == 2
    assert {item["track"]["name"] for item in mine["submissions"]} == {
        "Shared song",
        "Private song",
    }


def test_profile_paginates_history_and_keeps_removed_members_out(
    db: Session,
    make_round: Callable[..., Round],
    make_series: Callable[..., Series],
    make_track: Callable[..., Track],
    make_user: Callable[..., User],
) -> None:
    viewer = make_user(name="Viewer")
    contributor = make_user(name="Contributor")
    series = make_series()
    round_ = make_round(series, members=[viewer, contributor])
    for index in range(3):
        track = make_track(name=f"Track {index}", artist=f"Artist {index}")
        db.add(
            TrackArtist(
                track_id=track.id,
                spotify_artist_id=f"artist-{index}",
                name=f"Artist {index}",
                position=0,
            )
        )
        db.add(Submission(round_id=round_.id, contributor_id=contributor.id, track_id=track.id))
    db.commit()

    first_page = get_profile(contributor.id, db, viewer, limit=2)
    assert first_page["historyCount"] == 3
    assert len(first_page["submissions"]) == 2
    assert first_page["nextCursor"]
    second_page = get_profile(
        contributor.id, db, viewer, cursor=str(first_page["nextCursor"]), limit=2
    )
    assert len(second_page["submissions"]) == 1
    assert second_page["nextCursor"] is None

    membership = db.scalar(
        select(RoundMember).where(
            RoundMember.round_id == round_.id, RoundMember.user_id == viewer.id
        )
    )
    assert membership is not None
    membership.removed_at = round_.created_at
    db.commit()
    with pytest.raises(HTTPException, match="profile not found"):
        get_profile(contributor.id, db, viewer)


def test_profile_is_visible_to_series_and_platform_administrators(
    db: Session,
    make_round: Callable[..., Round],
    make_series: Callable[..., Series],
    make_track: Callable[..., Track],
    make_user: Callable[..., User],
) -> None:
    contributor = make_user(name="Contributor")
    series_admin = make_user(name="Series admin")
    platform_admin = make_user(name="Platform admin")
    platform_admin.platform_role = PlatformRole.ADMIN
    series = make_series()
    round_ = make_round(series, members=[contributor])
    track = make_track()
    db.add_all(
        (
            TrackArtist(
                track_id=track.id,
                spotify_artist_id="artist",
                name="Artist",
                position=0,
            ),
            Submission(round_id=round_.id, contributor_id=contributor.id, track_id=track.id),
            SeriesAdmin(series_id=series.id, user_id=series_admin.id),
        )
    )
    db.commit()

    assert get_profile(contributor.id, db, series_admin)["historyCount"] == 1
    assert get_profile(contributor.id, db, platform_admin)["historyCount"] == 1


def test_profile_does_not_reveal_unshared_contributor(
    db: Session,
    make_round: Callable[..., Round],
    make_series: Callable[..., Series],
    make_track: Callable[..., Track],
    make_user: Callable[..., User],
) -> None:
    listener = make_user(name="Listener")
    contributor = make_user(name="Contributor")
    series = make_series()
    private_round = make_round(series, members=[contributor])
    track = make_track()
    db.add(
        Submission(
            round_id=private_round.id,
            contributor_id=contributor.id,
            track_id=track.id,
            status=SubmissionStatus.ACCEPTED,
        )
    )
    db.commit()

    with pytest.raises(HTTPException, match="profile not found") as error:
        get_profile(contributor.id, db, listener)
    assert error.value.status_code == 404
