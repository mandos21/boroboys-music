"""Database access helpers for playlists and submissions."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import secrets
from typing import Iterable, Optional

from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import Session

from app.core.dates import normalize_month
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
    invite_token: Optional[str] = None,
    avatar_url: Optional[str] = None,
) -> models.User:
    statement: Select[tuple[models.User]] = select(models.User).where(
        models.User.spotify_user_id == spotify_user_id
    )
    user = session.scalar(statement)

    if user is None:
        role = "member"
        invite = None
        total_users = session.scalar(select(func.count()).select_from(models.User)) or 0
        if total_users == 0:
            role = "admin"
        else:
            if not invite_token:
                raise PermissionError("An invite is required to join this workspace.")
            invite = validate_invite(session, token=invite_token, email=email)
            role = invite.role

        user = models.User(
            username=username,
            display_name=display_name,
            email=email,
            role=role,
            spotify_user_id=spotify_user_id,
            spotify_avatar_url=avatar_url,
            spotify_access_token=access_token,
            spotify_refresh_token=refresh_token,
            spotify_token_expires_at=expires_at,
            spotify_scope=scope,
        )
        session.add(user)
        session.flush()
        if invite:
            invite.used_at = datetime.now(timezone.utc)
            invite.used_by_id = user.id
            session.add(invite)
    else:
        user.display_name = display_name
        user.email = email
        user.spotify_access_token = access_token
        user.spotify_token_expires_at = expires_at
        user.spotify_scope = scope
        user.spotify_user_id = spotify_user_id
        user.spotify_avatar_url = avatar_url or user.spotify_avatar_url
        if refresh_token:
            user.spotify_refresh_token = refresh_token
    session.flush()
    session.refresh(user)
    return user


def validate_invite(session: Session, *, token: str, email: Optional[str]) -> models.Invite:
    invite = session.scalar(
        select(models.Invite).where(
            and_(
                models.Invite.token == token,
                models.Invite.used_at.is_(None),
            )
        )
    )
    if invite is None:
        raise PermissionError("Invalid or already used invite token.")

    if invite.expires_at and invite.expires_at < datetime.now(timezone.utc):
        raise PermissionError("This invite has expired.")

    if invite.email and email:
        if invite.email.lower() != email.lower():
            raise PermissionError("Invite email does not match your Spotify account email.")
    elif invite.email and not email:
        raise PermissionError("This invite requires an email match. Enable email scope in Spotify permissions and try again.")

    return invite


def create_invite(
    session: Session,
    *,
    created_by: models.User,
    email: Optional[str] = None,
    role: str = "member",
    expires_in_days: int = 7,
) -> models.Invite:
    token = secrets.token_urlsafe(16)
    expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)
    invite = models.Invite(
        token=token,
        email=email,
        role=role,
        created_by_id=created_by.id,
        expires_at=expires_at,
    )
    session.add(invite)
    session.flush()
    session.refresh(invite)
    return invite


def get_month_settings(session: Session, month: datetime) -> Optional[models.MonthSettings]:
    month = normalize_month(month)
    statement: Select[tuple[models.MonthSettings]] = select(models.MonthSettings).where(
        models.MonthSettings.month == month
    )
    return session.scalar(statement)


def get_or_create_month_settings(
    session: Session,
    month: datetime,
    *,
    default_submission_limit: Optional[int] = 3,
    spotify_owner_id: Optional[str] = None,
) -> models.MonthSettings:
    month = normalize_month(month)
    settings = get_month_settings(session, month)
    if settings is None:
        settings = models.MonthSettings(
            month=month,
            submission_limit=default_submission_limit,
            spotify_owner_id=spotify_owner_id,
        )
        session.add(settings)
        session.flush()
        session.refresh(settings)
    return settings


def update_month_settings(
    session: Session,
    month: datetime,
    *,
    submission_limit: Optional[int] = None,
    spotify_owner_id: Optional[str] = None,
) -> models.MonthSettings:
    settings = get_or_create_month_settings(
        session,
        month,
        default_submission_limit=submission_limit,
        spotify_owner_id=spotify_owner_id,
    )
    settings.submission_limit = submission_limit
    settings.spotify_owner_id = spotify_owner_id
    session.flush()
    session.refresh(settings)
    return settings


def list_invites(session: Session, *, include_used: bool = False) -> Iterable[models.Invite]:
    statement = select(models.Invite).order_by(models.Invite.created_at.desc())
    if not include_used:
        statement = statement.where(models.Invite.used_at.is_(None))
    return session.scalars(statement).all()


def list_users(session: Session) -> Iterable[models.User]:
    statement = select(models.User).order_by(models.User.display_name, models.User.username)
    return session.scalars(statement).all()


def upsert_playlist(
    session: Session,
    *,
    name: str,
    month: datetime,
    description: Optional[str] = None,
    spotify_playlist_id: Optional[str] = None,
) -> models.Playlist:
    if month.tzinfo is None:
        month = month.replace(tzinfo=timezone.utc)
    else:
        month = month.astimezone(timezone.utc)

    playlist = session.scalar(
        select(models.Playlist).where(models.Playlist.month == month)
    )
    if playlist is None:
        playlist = models.Playlist(
            name=name,
            description=description,
            month=month,
            spotify_playlist_id=spotify_playlist_id,
        )
        session.add(playlist)
    else:
        playlist.name = name
        playlist.description = description
        playlist.spotify_playlist_id = spotify_playlist_id
    session.flush()
    session.refresh(playlist)
    return playlist


def add_playlist_track(
    session: Session,
    *,
    playlist: models.Playlist,
    track: models.Track,
    position: Optional[int] = None,
    submitter_id: Optional[int] = None,
    submitter_notes: Optional[str] = None,
) -> models.PlaylistTrack:
    entry = session.scalar(
        select(models.PlaylistTrack).where(
            models.PlaylistTrack.playlist_id == playlist.id,
            models.PlaylistTrack.track_id == track.id,
        )
    )
    if entry is None:
        if position is None:
            next_position = session.scalar(
                select(func.max(models.PlaylistTrack.position)).where(
                    models.PlaylistTrack.playlist_id == playlist.id
                )
            )
            position = (next_position or 0) + 1
        entry = models.PlaylistTrack(
            playlist_id=playlist.id,
            track_id=track.id,
            position=position,
            submitter_id=submitter_id,
            submitter_notes=submitter_notes,
        )
        session.add(entry)
    else:
        if position is not None:
            entry.position = position
        entry.submitter_id = submitter_id
        entry.submitter_notes = submitter_notes
    session.flush()
    session.refresh(entry)
    return entry


def list_submissions_for_month(session: Session, month: datetime) -> Iterable[models.Submission]:
    month = normalize_month(month)
    statement = select(models.Submission).where(
        models.Submission.submission_month == month
    ).order_by(models.Submission.created_at.asc())
    return session.scalars(statement).unique().all()


def count_user_submissions_for_month(session: Session, month: datetime, user_id: int) -> int:
    month = normalize_month(month)
    statement = select(func.count(models.Submission.id)).where(
        models.Submission.submission_month == month,
        models.Submission.user_id == user_id,
    )
    return session.scalar(statement) or 0


def user_has_locked_submission(session: Session, month: datetime, user_id: int) -> bool:
    month = normalize_month(month)
    statement = select(func.count(models.Submission.id)).where(
        models.Submission.submission_month == month,
        models.Submission.user_id == user_id,
        models.Submission.is_locked.is_(True),
    )
    return bool(session.scalar(statement))


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
    artwork_url: Optional[str] = None,
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
            artwork_url=artwork_url,
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
        track.artwork_url = artwork_url
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


def list_playlists(session: Session, *, limit: Optional[int] = 12) -> Iterable[models.Playlist]:
    statement = select(models.Playlist).order_by(models.Playlist.month.desc())
    if limit is not None:
        statement = statement.limit(limit)
    return session.scalars(statement).all()


def get_playlist_by_month(session: Session, month: datetime) -> Optional[models.Playlist]:
    statement = select(models.Playlist).where(models.Playlist.month == month)
    return session.scalar(statement)
