"""Track enrichment is intentionally additive and never a submit-path dependency."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cli.backfill_historical_track_metadata import _eligible_tracks
from app.db.models import Track, TrackArtist, TrackGenre
from app.services import spotify
from app.services.track_metadata import (
    refresh_track_genres,
    store_track_genres,
    sync_track_artists,
)


def test_genre_refresh_adds_to_existing_cached_metadata(
    db: Session,
    make_track: Callable[..., Track],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    track = make_track(provider_metadata={"genres": ["older tag"]})
    db.add(
        TrackArtist(
            track_id=track.id,
            spotify_artist_id="spotify-artist",
            name="A trusted artist",
            position=0,
        )
    )
    db.commit()
    monkeypatch.setattr("app.services.track_metadata.get_settings", lambda: _SpotifySettings())
    monkeypatch.setattr(spotify, "client_credentials_token", lambda _settings: "application-token")
    monkeypatch.setattr(
        spotify,
        "artists_by_id",
        lambda _token, artist_ids: [{"id": artist_ids[0], "genres": ["fresh tag"]}],
    )

    refresh_track_genres(db, track.id)

    db.expire_all()
    refreshed = db.get(Track, track.id)
    assert refreshed is not None
    assert refreshed.provider_metadata["genres"] == ["fresh tag", "older tag"]
    assert {
        genre.name
        for genre in db.scalars(select(TrackGenre).where(TrackGenre.track_id == track.id))
    } == {"fresh tag"}


class _SpotifySettings:
    spotify_is_configured = True


def test_a_refresh_within_the_interval_makes_no_remote_call(
    db: Session,
    make_track: Callable[..., Track],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cache is what keeps the backfill resumable and re-runnable."""
    track = make_track(
        provider_metadata={"genreEnrichmentCheckedAt": datetime.now(UTC).isoformat()}
    )
    db.add(
        TrackArtist(
            track_id=track.id, spotify_artist_id="spotify-artist", name="Artist", position=0
        )
    )
    db.commit()

    def unexpected(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("a fresh genre check must not call Spotify")

    monkeypatch.setattr(spotify, "client_credentials_token", unexpected)
    refresh_track_genres(db, track.id)


def test_genres_are_only_ever_added(db: Session, make_track: Callable[..., Track]) -> None:
    """Spotify dropping a tag must not erase what was already observed."""
    track = make_track(provider_metadata={"genres": ["shoegaze"]})
    store_track_genres(db, track, {"dream pop"})
    db.flush()

    assert track.provider_metadata["genres"] == ["dream pop", "shoegaze"]
    assert {
        row.name for row in db.scalars(select(TrackGenre).where(TrackGenre.track_id == track.id))
    } == {"dream pop"}


def test_storing_the_same_genre_twice_is_idempotent(
    db: Session, make_track: Callable[..., Track]
) -> None:
    track = make_track()
    assert store_track_genres(db, track, {"Shoegaze"}) == 1
    db.flush()
    # A second pass sees the same tag under a different case and must not
    # duplicate the row, which the composite primary key would reject anyway.
    store_track_genres(db, track, {"shoegaze"})
    db.flush()

    rows = list(db.scalars(select(TrackGenre).where(TrackGenre.track_id == track.id)))
    assert len(rows) == 1


def test_canonical_artists_replace_the_legacy_placeholder(
    db: Session, make_track: Callable[..., Track]
) -> None:
    """The migration seeds a `legacy:` credit; a real lookup must clear it."""
    track = make_track(artist="The Only Name We Had")
    sync_track_artists(db, track, [])
    db.flush()
    seeded = list(db.scalars(select(TrackArtist).where(TrackArtist.track_id == track.id)))
    assert [artist.spotify_artist_id for artist in seeded] == [f"legacy:{track.id}"]

    sync_track_artists(db, track, [("artist-a", "Artist A", 0), ("artist-b", "Artist B", 1)])
    db.flush()

    resolved = list(
        db.scalars(
            select(TrackArtist)
            .where(TrackArtist.track_id == track.id)
            .order_by(TrackArtist.position)
        )
    )
    assert [artist.spotify_artist_id for artist in resolved] == ["artist-a", "artist-b"]


def test_a_track_with_a_legacy_credit_is_still_eligible_for_backfill(
    db: Session, make_track: Callable[..., Track]
) -> None:
    """Resumability depends on this: a placeholder is not a resolved track.

    Both tracks carry a fresh genre timestamp so the stale-genre condition
    cannot be what makes either one eligible - the missing canonical artist
    has to be.
    """
    unresolved = make_track()
    sync_track_artists(db, unresolved, [])
    store_track_genres(db, unresolved, set())
    resolved = make_track()
    sync_track_artists(db, resolved, [("artist-a", "Artist A", 0)])
    store_track_genres(db, resolved, {"shoegaze"})
    db.commit()

    eligible = {track.id for track in _eligible_tracks(db, None, False, None)}

    assert unresolved.id in eligible
    assert resolved.id not in eligible
