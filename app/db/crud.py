"""Database access helpers for playlists and submissions."""
from __future__ import annotations

from datetime import date, datetime
from typing import Iterable, Optional

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.db import models


def get_user_by_username(session: Session, username: str) -> Optional[models.User]:
    statement: Select[tuple[models.User]] = select(models.User).where(models.User.username == username)
    return session.scalar(statement)


def upsert_spotify_user(
    session: Session,
    *,
    spotify_user_id: str,
    username: str,
    display_name: str,
    email: Optional[str],
    access_token: str,
    refresh_token: Optional[str],
    expires_at: datetime,
    scope: str,
) -> models.User:
    statement: Select[tuple[models.User]] = select(models.User).where(
        models.User.spotify_user_id == spotify_user_id
    )
    user = session.scalar(statement)

    if user is None:
        user = models.User(
            username=username,
            display_name=display_name,
            email=email,
            role="member",
            spotify_user_id=spotify_user_id,
            spotify_access_token=access_token,
            spotify_refresh_token=refresh_token,
            spotify_token_expires_at=expires_at,
            spotify_scope=scope,
        )
        session.add(user)
    else:
        user.display_name = display_name
        user.email = email
        user.spotify_access_token = access_token
        user.spotify_token_expires_at = expires_at
        user.spotify_scope = scope
        user.spotify_user_id = spotify_user_id
        if refresh_token:
            user.spotify_refresh_token = refresh_token
    session.flush()
    session.refresh(user)
    return user


def upsert_track(
    session: Session,
    *,
    spotify_track_id: str,
    name: str,
    artist: str,
    album: Optional[str] = None,
    duration_ms: Optional[int] = None,
    release_date: Optional[date] = None,
    spotify_url: Optional[str] = None,
    genres: Optional[dict] = None,
    lastfm_tags: Optional[dict] = None,
) -> models.Track:
    track = session.scalar(
        select(models.Track).where(models.Track.spotify_track_id == spotify_track_id)
    )
    if track is None:
        track = models.Track(
            spotify_track_id=spotify_track_id,
            name=name,
            artist=artist,
            album=album,
            duration_ms=duration_ms,
            release_date=release_date,
            spotify_url=spotify_url,
            genres=genres or {},
            lastfm_tags=lastfm_tags or {},
        )
        session.add(track)
    else:
        track.name = name
        track.artist = artist
        track.album = album
        track.duration_ms = duration_ms
        track.release_date = release_date
        track.spotify_url = spotify_url
        track.genres = genres or {}
        track.lastfm_tags = lastfm_tags or {}
    return track


def create_submission(
    session: Session,
    *,
    user: models.User,
    track: models.Track,
    submission_month: datetime,
    notes: Optional[str] = None,
) -> models.Submission:
    submission = models.Submission(
        user=user,
        track=track,
        submission_month=submission_month,
        notes=notes,
    )
    session.add(submission)
    return submission


def list_playlists(session: Session, *, limit: int = 12) -> Iterable[models.Playlist]:
    statement = select(models.Playlist).order_by(models.Playlist.month.desc()).limit(limit)
    return session.scalars(statement).all()


def get_playlist_by_month(session: Session, month: datetime) -> Optional[models.Playlist]:
    statement = select(models.Playlist).where(models.Playlist.month == month)
    return session.scalar(statement)
