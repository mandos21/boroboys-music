"""Best-effort, durable enrichment of shared Spotify track metadata."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Track, TrackArtist, TrackGenre
from app.services import spotify

_GENRE_REFRESH_INTERVAL = timedelta(days=7)


def sync_track_artists(db: Session, track: Track, artists: Iterable[tuple[str, str, int]]) -> None:
    """Persist trusted artist IDs, replacing the migration's legacy placeholder."""
    credits = list(artists)
    if not credits:
        if not db.scalar(select(TrackArtist.track_id).where(TrackArtist.track_id == track.id)):
            db.add(
                TrackArtist(
                    track_id=track.id,
                    spotify_artist_id=f"legacy:{track.id}",
                    name=track.artist,
                    position=0,
                )
            )
            db.flush()
        return
    artist_ids = {artist_id for artist_id, _, _ in credits}
    db.execute(
        delete(TrackArtist).where(
            TrackArtist.track_id == track.id,
            TrackArtist.spotify_artist_id.not_in(artist_ids),
        )
    )
    existing = {
        artist.spotify_artist_id: artist
        for artist in db.scalars(select(TrackArtist).where(TrackArtist.track_id == track.id))
    }
    for artist_id, name, position in credits:
        persisted = existing.get(artist_id)
        if persisted is None:
            db.add(
                TrackArtist(
                    track_id=track.id,
                    spotify_artist_id=artist_id,
                    name=name,
                    position=position,
                )
            )
        else:
            persisted.name = name
            persisted.position = position
    db.flush()


def store_track_genres(db: Session, track: Track, genres: Iterable[str]) -> int:
    """Add genre tags and record a successful refresh without removing old tags."""
    cleaned = {genre.strip() for genre in genres if genre.strip()}
    for genre in cleaned:
        db.execute(
            insert(TrackGenre)
            .values(track_id=track.id, genre_key=genre.casefold(), name=genre)
            .on_conflict_do_nothing(index_elements=[TrackGenre.track_id, TrackGenre.genre_key])
        )
    existing = track.provider_metadata.get("genres")
    known = (
        {genre.strip() for genre in existing if isinstance(genre, str) and genre.strip()}
        if isinstance(existing, list)
        else set()
    )
    metadata: dict[str, Any] = dict(track.provider_metadata)
    if known or cleaned:
        metadata["genres"] = sorted(known | cleaned, key=str.casefold)
    metadata["genreEnrichmentCheckedAt"] = datetime.now(UTC).isoformat()
    track.provider_metadata = metadata
    return len(cleaned)


def refresh_track_genres(db: Session, track_id: uuid.UUID) -> None:
    """Refresh a track's genre cache without ever removing known values.

    This runs outside the submit path. Spotify metadata is helpful context for
    profiles, never a reason to slow down or reject a valid submission.
    """
    track = db.get(Track, track_id)
    if track is None or not _needs_genre_refresh(track.provider_metadata):
        return
    artist_ids = list(
        db.scalars(
            select(TrackArtist.spotify_artist_id).where(
                TrackArtist.track_id == track.id,
                ~TrackArtist.spotify_artist_id.startswith("legacy:"),
            )
        )
    )
    if not artist_ids or not get_settings().spotify_is_configured:
        return
    access_token = spotify.client_credentials_token(get_settings())
    artists = spotify.artists_by_id(access_token, artist_ids)
    genres = {
        genre.strip()
        for artist in artists
        for genre in (artist.get("genres") or [])
        if isinstance(genre, str) and genre.strip()
    }
    store_track_genres(db, track, genres)
    db.commit()


def _needs_genre_refresh(metadata: dict[str, Any]) -> bool:
    value = metadata.get("genreEnrichmentCheckedAt")
    if not isinstance(value, str):
        return True
    try:
        checked_at = datetime.fromisoformat(value)
    except ValueError:
        return True
    if checked_at.tzinfo is None:
        return True
    return checked_at < datetime.now(UTC) - _GENRE_REFRESH_INTERVAL
