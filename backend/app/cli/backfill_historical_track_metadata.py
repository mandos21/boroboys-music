"""Backfill canonical Spotify artists and cached genres for historical tracks.

The command is deliberately resumable. A normal run only selects tracks that
have no canonical artist credit or whose last successful genre lookup is older
than a week. It commits each batch independently and pauses between Spotify
requests, so it is safe to interrupt and run again.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Round, Series, Submission, Track, TrackArtist
from app.db.session import get_session_factory
from app.services import spotify
from app.services.track_metadata import (
    _needs_genre_refresh,
    store_track_genres,
    sync_track_artists,
)

_SPOTIFY_TRACK_ID = re.compile(r"^[A-Za-z0-9]{22}$")
_BATCH_SIZE = 50


@dataclass(frozen=True)
class BackfillResult:
    eligible: int
    resolved: int
    enriched: int
    missing_from_spotify: int
    skipped_invalid_id: int


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--series-slug",
        help="limit the backfill to tracks submitted in this series (defaults to all tracks)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="process at most this many eligible tracks; useful for a small first run",
    )
    parser.add_argument(
        "--pause-seconds",
        type=float,
        default=0.75,
        help="pause after each Spotify request (default: 0.75)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="refresh tracks even when their genre lookup is less than a week old",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="report eligible tracks without calling Spotify"
    )
    args = parser.parse_args()
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    if args.pause_seconds < 0:
        parser.error("--pause-seconds cannot be negative")
    if not get_settings().spotify_is_configured:
        print("Spotify application credentials are required for genre backfill.", file=sys.stderr)
        return 2

    try:
        with get_session_factory()() as db:
            tracks = _eligible_tracks(db, args.series_slug, args.force, args.limit)
            invalid = sum(
                not _SPOTIFY_TRACK_ID.fullmatch(track.spotify_track_id) for track in tracks
            )
            if args.dry_run:
                print(
                    f"Would inspect {len(tracks)} track(s): "
                    f"{len(tracks) - invalid} with Spotify IDs, {invalid} skipped "
                    "because their IDs are not Spotify track IDs."
                )
                return 0
            token = spotify.client_credentials_token(get_settings())
            result = _backfill_metadata(db, tracks, token, args.pause_seconds)
    except (spotify.SpotifyError, httpx.HTTPError) as error:
        print(f"Historical genre backfill failed: {error}", file=sys.stderr)
        return 2

    print(
        f"Resolved canonical metadata for {result.resolved} of "
        f"{result.eligible} eligible track(s); cached genres for {result.enriched}; "
        f"{result.missing_from_spotify} were unavailable; "
        f"skipped {result.skipped_invalid_id} non-Spotify ID(s)."
    )
    return 0


def _eligible_tracks(
    db: Session, series_slug: str | None, force: bool, limit: int | None
) -> list[Track]:
    statement = select(Track).order_by(Track.spotify_track_id)
    if series_slug is not None:
        statement = (
            statement.join(Submission, Submission.track_id == Track.id)
            .join(Round, Round.id == Submission.round_id)
            .join(Series, Series.id == Round.series_id)
            .where(Series.slug == series_slug)
            .distinct()
        )
    tracks = list(db.scalars(statement))
    canonical_track_ids = set(
        db.scalars(
            select(TrackArtist.track_id).where(~TrackArtist.spotify_artist_id.startswith("legacy:"))
        )
    )
    eligible = [
        track
        for track in tracks
        if force
        or track.id not in canonical_track_ids
        or _needs_genre_refresh(track.provider_metadata)
    ]
    return eligible[:limit] if limit is not None else eligible


def _backfill_metadata(
    db: Session, tracks: list[Track], access_token: str, pause_seconds: float
) -> BackfillResult:
    eligible = len(tracks)
    resolved = enriched = missing = invalid = 0
    valid_tracks = {
        track.spotify_track_id: track
        for track in tracks
        if _SPOTIFY_TRACK_ID.fullmatch(track.spotify_track_id)
    }
    invalid = eligible - len(valid_tracks)
    track_ids = list(valid_tracks)
    for start in range(0, len(track_ids), _BATCH_SIZE):
        batch_ids = track_ids[start : start + _BATCH_SIZE]
        response_tracks = spotify.tracks_by_id(access_token, batch_ids)
        time.sleep(pause_seconds)
        response_by_id = {item["id"] for item in response_tracks if isinstance(item.get("id"), str)}
        missing += len(set(batch_ids) - response_by_id)
        artists_by_track: dict[Track, list[tuple[str, str, int]]] = {}
        artist_ids: set[str] = set()
        for item in response_tracks:
            spotify_track_id = item.get("id")
            if (
                not isinstance(spotify_track_id, str)
                or (track := valid_tracks.get(spotify_track_id)) is None
            ):
                continue
            credits = _artist_credits(item)
            if not credits:
                continue
            artists_by_track[track] = credits
            artist_ids.update(artist_id for artist_id, _, _ in credits)
            album = item.get("album")
            if isinstance(album, dict):
                album_id = album.get("id")
                if isinstance(album_id, str):
                    track.spotify_album_id = album_id
                if track.album is None and isinstance(album.get("name"), str):
                    track.album = album["name"]
                images = album.get("images")
                if track.artwork_url is None and isinstance(images, list) and images:
                    image = images[0]
                    if isinstance(image, dict) and isinstance(image.get("url"), str):
                        track.artwork_url = image["url"]
            if track.spotify_uri is None and isinstance(item.get("uri"), str):
                track.spotify_uri = item["uri"]
            sync_track_artists(db, track, credits)
            resolved += 1

        genres_by_artist = _genres_by_artist(access_token, artist_ids, pause_seconds)
        for track, credits in artists_by_track.items():
            enriched += bool(
                store_track_genres(
                    db,
                    track,
                    {
                        genre
                        for artist_id, _, _ in credits
                        for genre in genres_by_artist.get(artist_id, set())
                    },
                )
            )
        db.commit()
    return BackfillResult(eligible, resolved, enriched, missing, invalid)


def _artist_credits(item: dict[str, object]) -> list[tuple[str, str, int]]:
    artists = item.get("artists")
    if not isinstance(artists, list):
        return []
    return [
        (artist["id"], artist["name"], position)
        for position, artist in enumerate(artists)
        if isinstance(artist, dict)
        and isinstance(artist.get("id"), str)
        and isinstance(artist.get("name"), str)
    ]


def _genres_by_artist(
    access_token: str, artist_ids: set[str], pause_seconds: float
) -> dict[str, set[str]]:
    genres: dict[str, set[str]] = {}
    ordered_ids = sorted(artist_ids)
    for start in range(0, len(ordered_ids), _BATCH_SIZE):
        for artist in spotify.artists_by_id(access_token, ordered_ids[start : start + _BATCH_SIZE]):
            artist_id = artist.get("id")
            if not isinstance(artist_id, str):
                continue
            genres[artist_id] = {
                genre.strip()
                for genre in (artist.get("genres") or [])
                if isinstance(genre, str) and genre.strip()
            }
        time.sleep(pause_seconds)
    return genres


if __name__ == "__main__":
    sys.exit(main())
