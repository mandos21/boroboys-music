from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import deps
from app.db import crud, models
from app.schemas import (
    PlaylistFinalizeRequest,
    PlaylistImportRequest,
    PlaylistImportResponse,
    PlaylistImportSaveRequest,
    PlaylistListResponse,
    PlaylistRead,
)

router = APIRouter(prefix="/playlists")


@router.get("", response_model=PlaylistListResponse)
def list_playlists(
    limit: Optional[int] = 12,
    db: Session = Depends(deps.get_db),
) -> PlaylistListResponse:
    playlists = crud.list_playlists(db, limit=limit)
    return PlaylistListResponse(items=[PlaylistRead.from_orm(playlist) for playlist in playlists])


@router.get("/{playlist_id}", response_model=PlaylistRead)
def read_playlist(playlist_id: int, db: Session = Depends(deps.get_db)) -> PlaylistRead:
    playlist = db.get(models.Playlist, playlist_id)
    if not playlist:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Playlist not found")
    return PlaylistRead.from_orm(playlist)


@router.post("/finalize", response_model=PlaylistRead)
def finalize_playlist(
    payload: PlaylistFinalizeRequest,
    manager=Depends(deps.get_playlist_manager),
    current_user: models.User = Depends(deps.require_admin),
    db: Session = Depends(deps.get_db),
) -> PlaylistRead:
    month = payload.month
    playlist = manager.finalize_month(
        month,
        admin_user_id=current_user.id,
        spotify_owner_id=payload.spotify_owner_id,
    )
    if playlist is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No submissions to finalize")

    refreshed = crud.get_playlist_by_month(db, playlist.month)
    if refreshed is None:
        refreshed = playlist
    return PlaylistRead.from_orm(refreshed)


@router.post("/import", response_model=PlaylistImportResponse)
def import_playlist(
    payload: PlaylistImportRequest,
    spotify=Depends(deps.get_spotify_service),
    _: models.User = Depends(deps.require_admin),
) -> PlaylistImportResponse:
    try:
        playlist_id = payload.extract_playlist_id()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    playlist_data = spotify.fetch_playlist_with_tracks(playlist_id)
    if not playlist_data:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unable to load Spotify playlist")

    return PlaylistImportResponse.from_spotify_payload(
        playlist_data,
        requested_month=payload.playlist_month,
    )


@router.post("/import/save", response_model=PlaylistRead)
def save_imported_playlist(
    payload: PlaylistImportSaveRequest,
    db: Session = Depends(deps.get_db),
    current_user: models.User = Depends(deps.require_admin),
) -> PlaylistRead:
    playlist_month_dt = payload.payload.month_datetime()

    playlist_db = crud.upsert_playlist(
        db,
        name=payload.payload.name,
        month=playlist_month_dt,
        description=payload.payload.description,
        spotify_playlist_id=payload.payload.spotify_playlist_id,
    )

    existing_entries = db.scalars(
        select(models.PlaylistTrack).where(models.PlaylistTrack.playlist_id == playlist_db.id)
    ).all()
    for entry in existing_entries:
        db.delete(entry)
    db.flush()

    assignments = {item.position: item for item in payload.assignments}
    user_cache: dict[int, models.User] = {}

    for track in payload.payload.tracks:
        track_db = crud.upsert_track(
            db,
            spotify_track_id=track.spotify_track_id,
            name=track.name,
            artist=track.artists,
            album=track.album,
            duration_ms=track.duration_ms,
            spotify_url=track.spotify_url,
        )
        db.flush()
        crud.add_playlist_track(
            db,
            playlist=playlist_db,
            track=track_db,
            position=track.position,
        )

        assignment = assignments.get(track.position)
        if assignment and assignment.user_id is not None:
            user = user_cache.get(assignment.user_id)
            if user is None:
                user = db.get(models.User, assignment.user_id)
                if user is None:
                    continue
                user_cache[user.id] = user
            crud.create_or_update_submission(
                db,
                user=user,
                track=track_db,
                submission_month=playlist_month_dt,
                notes=assignment.notes,
                is_locked=payload.lock_submissions,
            )

    playlist_db.finalized_by = current_user.id
    db.commit()
    db.refresh(playlist_db)
    return PlaylistRead.from_orm(playlist_db)
