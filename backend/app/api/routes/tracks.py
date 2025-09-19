from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api import deps
from app.db import models
from app.core.state import extract_track_identifier
from app.schemas import SpotifyTrackResult, TrackRead
from app.services.spotify_service import SpotifyService

router = APIRouter(prefix="/tracks")


@router.get("/search", response_model=List[SpotifyTrackResult])
def search_tracks(
    query: str = Query(..., min_length=2),
    limit: int = Query(10, gt=0, le=50),
    spotify: SpotifyService = Depends(deps.get_spotify_service),
) -> List[SpotifyTrackResult]:
    results = spotify.search_tracks(query, limit=limit)
    parsed: List[SpotifyTrackResult] = []
    for item in results:
        track_id = item.get("id")
        if not track_id:
            continue
        artists = ", ".join(artist.get("name", "") for artist in item.get("artists", []))
        parsed.append(
            SpotifyTrackResult(
                spotify_track_id=track_id,
                name=item.get("name", ""),
                artist=artists,
                album=item.get("album", {}).get("name"),
                duration_ms=item.get("duration_ms"),
                spotify_url=(item.get("external_urls") or {}).get("spotify"),
                artwork_url=SpotifyService.pick_image_url(
                    (item.get("album") or {}).get("images")
                ),
            )
        )
    return parsed


@router.get("/resolve", response_model=SpotifyTrackResult)
def resolve_track(
    ref: str = Query(..., min_length=2),
    spotify: SpotifyService = Depends(deps.get_spotify_service),
) -> SpotifyTrackResult:
    track_identifier = extract_track_identifier(ref)
    if not track_identifier or len(track_identifier) < 5:  # pragma: no cover - defensive
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provide a valid Spotify track reference")

    track = spotify.fetch_track(track_identifier)
    if not track:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Spotify track not found")

    album = track.get("album") or {}
    artists = ", ".join(artist.get("name", "") for artist in track.get("artists", []))

    return SpotifyTrackResult(
        spotify_track_id=track.get("id", track_identifier),
        name=track.get("name", ""),
        artist=artists,
        album=album.get("name"),
        duration_ms=track.get("duration_ms"),
        spotify_url=(track.get("external_urls") or {}).get("spotify"),
        artwork_url=SpotifyService.pick_image_url(album.get("images")),
    )


@router.get("/{track_id}", response_model=TrackRead)
def read_track(
    track_id: int,
    db: Session = Depends(deps.get_db),
) -> TrackRead:
    track = db.get(models.Track, track_id)
    if not track:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Track not found")
    return TrackRead.from_orm(track)
