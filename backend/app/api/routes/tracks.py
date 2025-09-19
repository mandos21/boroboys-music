from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api import deps
from app.db import crud, models
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
            )
        )
    return parsed


@router.get("/{track_id}", response_model=TrackRead)
def read_track(
    track_id: int,
    db: Session = Depends(deps.get_db),
) -> TrackRead:
    track = db.get(models.Track, track_id)
    if not track:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Track not found")
    return TrackRead.from_orm(track)
