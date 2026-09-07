"""Populate missing track artwork using Spotify metadata credentials."""

from __future__ import annotations

import argparse
import re
import sys
import time
import uuid

import httpx
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import Track
from app.db.session import get_session_factory
from app.services import spotify
from app.services.publications import PublicationError, get_spotify_access_token

_SPOTIFY_TRACK_ID = re.compile(r"^[A-Za-z0-9]{22}$")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--publisher-account-id",
        type=uuid.UUID,
        help="linked Spotify account that is allowed to read Spotify metadata",
    )
    parser.add_argument(
        "--client-credentials",
        action="store_true",
        help="use configured Spotify application credentials for public track metadata",
    )
    parser.add_argument(
        "--pause-seconds",
        type=float,
        default=0.35,
        help="pause between batches of 50 tracks (default: 0.35)",
    )
    args = parser.parse_args()
    if bool(args.publisher_account_id) == args.client_credentials:
        parser.error("provide exactly one of --publisher-account-id or --client-credentials")
    if args.pause_seconds < 0:
        parser.error("--pause-seconds cannot be negative")

    try:
        with get_session_factory()() as db:
            tracks = list(
                db.scalars(
                    select(Track)
                    .where(Track.artwork_url.is_(None))
                    .order_by(Track.spotify_track_id)
                )
            )
            token = (
                spotify.client_credentials_token(get_settings())
                if args.client_credentials
                else get_spotify_access_token(db, args.publisher_account_id)
            )
            updated, eligible = _backfill_artwork(tracks, token, args.pause_seconds)
            db.commit()
    except (PublicationError, spotify.SpotifyError, httpx.HTTPError) as error:
        print(f"Artwork backfill failed: {error}", file=sys.stderr)
        return 2

    print(
        f"Updated artwork for {updated} of {eligible} Spotify track(s); "
        f"skipped {len(tracks) - eligible} local record(s) without a Spotify track ID."
    )
    return 0


def _backfill_artwork(
    tracks: list[Track], access_token: str, pause_seconds: float
) -> tuple[int, int]:
    by_spotify_id = {
        track.spotify_track_id: track
        for track in tracks
        if _SPOTIFY_TRACK_ID.fullmatch(track.spotify_track_id)
    }
    updated = 0
    track_ids = list(by_spotify_id)
    for start in range(0, len(track_ids), 50):
        for item in spotify.tracks_by_id(access_token, track_ids[start : start + 50]):
            track_id = item.get("id")
            album = item.get("album")
            images = album.get("images") if isinstance(album, dict) else None
            if not isinstance(track_id, str) or not isinstance(images, list) or not images:
                continue
            image = images[0]
            url = image.get("url") if isinstance(image, dict) else None
            track = by_spotify_id.get(track_id)
            if track is not None and isinstance(url, str):
                track.artwork_url = url
                updated += 1
        if start + 50 < len(track_ids):
            time.sleep(pause_seconds)
    return updated, len(track_ids)


if __name__ == "__main__":
    sys.exit(main())
