"""Pydantic schemas shared between the Streamlit UI and service layer."""
from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class TrackBase(BaseModel):
    spotify_track_id: str
    name: str
    artist: str
    album: Optional[str] = None
    duration_ms: Optional[int] = None
    release_date: Optional[date] = None
    spotify_url: Optional[str] = None
    genres: List[str] = Field(default_factory=list)
    lastfm_tags: List[str] = Field(default_factory=list)


class TrackRead(TrackBase):
    id: int


class SubmissionBase(BaseModel):
    submission_month: datetime
    notes: Optional[str] = None


class SubmissionCreate(SubmissionBase):
    track: TrackBase


class SubmissionRead(SubmissionBase):
    id: int
    user_id: int
    track: TrackRead
    is_locked: bool


class PlaylistTrackRead(BaseModel):
    track: TrackRead
    position: int


class PlaylistRead(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    month: datetime
    spotify_playlist_id: Optional[str] = None
    tracks: List[PlaylistTrackRead] = Field(default_factory=list)


class ListeningStatRead(BaseModel):
    user_id: int
    track_id: int
    lastfm_playcount: int
    lastfm_last_listened_at: Optional[datetime] = None
    snapshot_at: datetime


class SongLookupResult(BaseModel):
    track: TrackRead
    submissions: List[SubmissionRead] = Field(default_factory=list)
    playlists: List[PlaylistRead] = Field(default_factory=list)