"""SQLAlchemy ORM models for the playlist application."""
from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(20), default="member", nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(150))
    password_hash: Mapped[Optional[str]] = mapped_column(String(255))
    spotify_user_id: Mapped[Optional[str]] = mapped_column(String(120))
    spotify_access_token: Mapped[Optional[str]] = mapped_column(String(512))
    spotify_refresh_token: Mapped[Optional[str]] = mapped_column(String(512))
    spotify_token_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    spotify_scope: Mapped[Optional[str]] = mapped_column(String(250))
    lastfm_username: Mapped[Optional[str]] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    submissions: Mapped[List["Submission"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    playlists_finalized: Mapped[List["Playlist"]] = relationship(back_populates="finalized_by_user")
    invites_sent: Mapped[List["Invite"]] = relationship(
        back_populates="created_by",
        foreign_keys="Invite.created_by_id",
    )
    invites_used: Mapped[List["Invite"]] = relationship(
        back_populates="used_by",
        foreign_keys="Invite.used_by_id",
    )


class Track(Base):
    __tablename__ = "tracks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    spotify_track_id: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    artist: Mapped[str] = mapped_column(String(200), nullable=False)
    album: Mapped[Optional[str]] = mapped_column(String(200))
    duration_ms: Mapped[Optional[int]]
    release_date: Mapped[Optional[date]] = mapped_column(Date)
    spotify_url: Mapped[Optional[str]] = mapped_column(String(250))
    genres: Mapped[dict] = mapped_column(JSONB, default=dict)
    lastfm_tags: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    submissions: Mapped[List["Submission"]] = relationship(
        back_populates="track", cascade="all, delete-orphan"
    )
    playlist_entries: Mapped[List["PlaylistTrack"]] = relationship(back_populates="track")


class Submission(Base):
    __tablename__ = "submissions"
    __table_args__ = (UniqueConstraint("user_id", "submission_month", name="uq_user_month"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False)
    submission_month: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(String(500))
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="submissions")
    track: Mapped[Track] = relationship(back_populates="submissions")


class Playlist(Base):
    __tablename__ = "playlists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(500))
    month: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, unique=True)
    spotify_playlist_id: Mapped[Optional[str]] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    finalized_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"))

    finalized_by_user: Mapped[Optional[User]] = relationship(back_populates="playlists_finalized")
    tracks: Mapped[List["PlaylistTrack"]] = relationship(
        back_populates="playlist", cascade="all, delete-orphan"
    )


class PlaylistTrack(Base):
    __tablename__ = "playlist_tracks"
    __table_args__ = (UniqueConstraint("playlist_id", "track_id", name="uq_playlist_track"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    playlist_id: Mapped[int] = mapped_column(ForeignKey("playlists.id", ondelete="CASCADE"), nullable=False)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    playlist: Mapped[Playlist] = relationship(back_populates="tracks")
    track: Mapped[Track] = relationship(back_populates="playlist_entries")


class ListeningStat(Base):
    __tablename__ = "listening_stats"
    __table_args__ = (UniqueConstraint("user_id", "track_id", "snapshot_at", name="uq_listening_snapshot"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False)
    lastfm_playcount: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lastfm_last_listened_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped[User] = relationship()
    track: Mapped[Track] = relationship()


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(150))
    role: Mapped[str] = mapped_column(String(20), default="member", nullable=False)
    created_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    used_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    created_by: Mapped[Optional[User]] = relationship(
        back_populates="invites_sent",
        foreign_keys=[created_by_id],
    )
    used_by: Mapped[Optional[User]] = relationship(
        back_populates="invites_used",
        foreign_keys=[used_by_id],
    )
