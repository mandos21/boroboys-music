"""Profile history is useful only when it respects the existing round boundary."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.profiles import (
    NotificationSettingsUpdate,
    get_my_profile,
    get_notification_settings,
    get_profile,
    update_notification_settings,
)
from app.db.models import (
    PlatformRole,
    Round,
    RoundMember,
    RoundStatus,
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
    shared_round = make_round(series, members=[listener, contributor], status=RoundStatus.PUBLISHED)
    private_round = make_round(series, members=[contributor], status=RoundStatus.PUBLISHED)
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
    # Each genre carries the group it belongs to, so the client colours related
    # genres alike rather than by their position in the list. Both sit under
    # the tree's alternative rock branch, which naive matching on the trailing
    # word would have called pop and rock respectively.
    assert visible["stats"]["genreSpread"] == [
        {"name": "dream pop", "count": 1, "group": "alternative"},
        {"name": "indie rock", "count": 1, "group": "alternative"},
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
    round_ = make_round(series, members=[viewer, contributor], status=RoundStatus.PUBLISHED)
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


def test_profile_keeps_ten_artists_and_every_cached_genre(
    db: Session,
    make_round: Callable[..., Round],
    make_series: Callable[..., Series],
    make_track: Callable[..., Track],
    make_user: Callable[..., User],
) -> None:
    viewer = make_user(name="Viewer")
    contributor = make_user(name="Contributor")
    series = make_series()
    round_ = make_round(series, members=[viewer, contributor], status=RoundStatus.PUBLISHED)
    for index in range(31):
        track = make_track(name=f"Track {index}", artist=f"Artist {index}")
        db.add_all(
            (
                TrackArtist(
                    track_id=track.id,
                    spotify_artist_id=f"artist-{index}",
                    name=f"Artist {index}",
                    position=0,
                ),
                TrackGenre(track_id=track.id, genre_key=f"genre-{index}", name=f"Genre {index}"),
                Submission(round_id=round_.id, contributor_id=contributor.id, track_id=track.id),
            )
        )
    db.commit()

    profile = get_profile(contributor.id, db, viewer)

    assert len(profile["stats"]["topArtists"]) == 10
    assert len(profile["stats"]["genreSpread"]) == 31


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
    round_ = make_round(series, members=[contributor], status=RoundStatus.PUBLISHED)
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


def test_profile_hides_submissions_from_rounds_that_have_not_published_yet(
    db: Session,
    make_round: Callable[..., Round],
    make_series: Callable[..., Series],
    make_track: Callable[..., Track],
    make_user: Callable[..., User],
) -> None:
    """A round's picks stay off every profile - even the contributor's own -

    until its playlist publishes, the same secret the round page itself
    keeps while a round is open.
    """
    viewer = make_user(name="Viewer")
    contributor = make_user(name="Contributor")
    series = make_series()
    open_round = make_round(series, members=[viewer, contributor], status=RoundStatus.OPEN)
    closed_round = make_round(series, members=[viewer, contributor], status=RoundStatus.CLOSED)
    published_round = make_round(
        series, members=[viewer, contributor], status=RoundStatus.PUBLISHED
    )
    for round_ in (open_round, closed_round, published_round):
        track = make_track(name=f"Track for {round_.status.value}", artist="Artist")
        db.add(Submission(round_id=round_.id, contributor_id=contributor.id, track_id=track.id))
    db.commit()

    visible = get_profile(contributor.id, db, viewer)
    assert visible["stats"]["submissionCount"] == 1
    assert [item["track"]["name"] for item in visible["submissions"]] == ["Track for published"]

    # Not even the contributor's own profile reveals the other two early.
    own = get_my_profile(db, contributor)
    assert own["stats"]["submissionCount"] == 1
    assert [item["track"]["name"] for item in own["submissions"]] == ["Track for published"]


def test_notification_settings_default_to_enabled_and_can_be_toggled_independently(
    db: Session, make_user: Callable[..., User]
) -> None:
    user = make_user(name="Settings")
    db.commit()

    defaults = get_notification_settings(user)
    assert defaults == {"notifyReminderEmails": True, "notifyRoundPublishedEmails": True}

    updated = update_notification_settings(
        NotificationSettingsUpdate(notify_reminder_emails=False), db, user
    )
    assert updated == {"notifyReminderEmails": False, "notifyRoundPublishedEmails": True}
    assert get_notification_settings(user) == updated

    restored = update_notification_settings(
        NotificationSettingsUpdate(notify_reminder_emails=True), db, user
    )
    assert restored == {"notifyReminderEmails": True, "notifyRoundPublishedEmails": True}


def test_affinity_ranks_listeners_from_shared_visible_rounds_only(
    db: Session,
    make_round: Callable[..., Round],
    make_series: Callable[..., Series],
    make_track: Callable[..., Track],
    make_user: Callable[..., User],
) -> None:
    viewer = make_user(name="Viewer")
    profile = make_user(name="Profile")
    kindred = make_user(name="Kindred")
    stranger = make_user(name="Stranger")
    series = make_series()
    shared = make_round(
        series,
        members=[viewer, profile, kindred],
        submission_limit=2,
        status=RoundStatus.PUBLISHED,
    )
    hidden = make_round(series, members=[profile, stranger], status=RoundStatus.PUBLISHED)

    def tagged(name: str, *genres: str) -> Track:
        track = make_track(name=name, artist=name)
        db.add_all(TrackGenre(track_id=track.id, genre_key=genre, name=genre) for genre in genres)
        return track

    db.add_all(
        (
            Submission(
                round_id=shared.id,
                contributor_id=profile.id,
                track_id=tagged("P1", "indie rock").id,
                status=SubmissionStatus.ACCEPTED,
            ),
            Submission(
                round_id=shared.id,
                contributor_id=profile.id,
                track_id=tagged("P2", "dream pop").id,
                status=SubmissionStatus.ACCEPTED,
            ),
            Submission(
                round_id=shared.id,
                contributor_id=kindred.id,
                track_id=tagged("K1", "indie rock").id,
                status=SubmissionStatus.ACCEPTED,
            ),
            Submission(
                round_id=hidden.id,
                contributor_id=profile.id,
                track_id=tagged("P3", "ambient").id,
                status=SubmissionStatus.ACCEPTED,
            ),
            Submission(
                round_id=hidden.id,
                contributor_id=stranger.id,
                track_id=tagged("S1", "indie rock", "dream pop").id,
                status=SubmissionStatus.ACCEPTED,
            ),
        )
    )
    db.commit()

    affinity = get_profile(profile.id, db, viewer)["stats"]["affinity"]

    assert [item["displayName"] for item in affinity] == ["Kindred"]
    assert affinity[0]["sharedRoundCount"] == 1
    assert affinity[0]["sharedGenres"] == ["indie rock"]
    assert affinity[0]["affinity"] == 100  # both entirely within the alternative family

    # The profile's owner can see the hidden round, so the stranger shows up for them.
    own = get_my_profile(db, profile)["stats"]["affinity"]
    assert {item["displayName"] for item in own} == {"Kindred", "Stranger"}
