"""Pydantic schemas used by the API layer."""
from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.state import extract_playlist_identifier


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


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
    artwork_url: Optional[str] = None

    @field_validator("genres", "lastfm_tags", mode="before")
    @classmethod
    def _coerce_list(cls, value):
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item) for item in value]
        if isinstance(value, dict):
            for key in ("items", "tags"):
                items = value.get(key)
                if isinstance(items, list):
                    return [str(item) for item in items]
            return [str(item) for item in value.values()]
        return [str(value)] if value not in ("", None) else []


class TrackRead(TrackBase, ORMModel):
    id: int


class SpotifyTrackResult(BaseModel):
    spotify_track_id: str
    name: str
    artist: str
    album: Optional[str] = None
    duration_ms: Optional[int] = None
    spotify_url: Optional[str] = None
    artwork_url: Optional[str] = None


class SubmissionBase(BaseModel):
    submission_month: datetime
    notes: Optional[str] = None


class SubmissionCreate(SubmissionBase):
    track: TrackBase


class SubmissionUpdate(BaseModel):
    submission_month: Optional[datetime] = None
    notes: Optional[str] = None
    track: Optional[TrackBase] = None
    is_locked: Optional[bool] = None


class SubmissionRead(SubmissionBase, ORMModel):
    id: int
    user_id: int
    track: TrackRead
    is_locked: bool


class SubmissionListResponse(BaseModel):
    items: List[SubmissionRead]


class PlaylistTrackRead(ORMModel):
    track: TrackRead
    position: int
    submitter_id: Optional[int] = None
    submitter_name: Optional[str] = None
    submitter_notes: Optional[str] = None
    submitter_avatar_url: Optional[str] = None

class PlaylistRead(ORMModel):
    id: int
    name: str
    description: Optional[str] = None
    month: datetime
    spotify_playlist_id: Optional[str] = None
    tracks: List[PlaylistTrackRead] = Field(default_factory=list)


class PlaylistListResponse(BaseModel):
    items: List[PlaylistRead]


class PlaylistFinalizeRequest(BaseModel):
    month: datetime
    spotify_owner_id: Optional[str] = None


class PlaylistImportRequest(BaseModel):
    playlist_ref: str
    playlist_month: str

    @field_validator("playlist_month")
    @classmethod
    def validate_month(cls, value: str) -> str:
        try:
            datetime.strptime(value, "%Y-%m")
        except ValueError as exc:  # pragma: no cover - simple validation
            raise ValueError("Month must be in YYYY-MM format") from exc
        return value

    def extract_playlist_id(self) -> str:
        identifier = extract_playlist_identifier(self.playlist_ref)
        if not identifier:
            raise ValueError("Provide a valid Spotify playlist reference")
        return identifier


class PlaylistImportTrack(BaseModel):
    spotify_track_id: str
    name: str
    artists: str
    album: Optional[str] = None
    duration_ms: Optional[int] = None
    position: int
    spotify_url: Optional[str] = None
    artwork_url: Optional[str] = None


class PlaylistImportResponse(BaseModel):
    spotify_playlist_id: str
    name: str
    description: Optional[str] = None
    playlist_month: str
    snapshot_id: Optional[str] = None
    tracks: List[PlaylistImportTrack] = Field(default_factory=list)

    @classmethod
    def from_spotify_payload(cls, payload: Dict, *, requested_month: str) -> "PlaylistImportResponse":
        tracks: List[PlaylistImportTrack] = []
        for index, item in enumerate(payload.get("tracks", [])):
            track_id = item.get("spotify_track_id")
            if not track_id:
                continue
            tracks.append(
                PlaylistImportTrack(
                    spotify_track_id=track_id,
                    name=item.get("name", ""),
                    artists=item.get("artists", ""),
                    album=item.get("album"),
                    duration_ms=item.get("duration_ms"),
                    position=item.get("position") or index + 1,
                    spotify_url=item.get("spotify_url"),
                    artwork_url=item.get("artwork_url"),
                )
            )
        return cls(
            spotify_playlist_id=payload.get("id", ""),
            name=payload.get("name", "Imported Playlist"),
            description=payload.get("description"),
            playlist_month=requested_month,
            snapshot_id=payload.get("snapshot_id"),
            tracks=tracks,
        )

    def month_datetime(self) -> datetime:
        return datetime.strptime(self.playlist_month, "%Y-%m").replace(day=1)


class PlaylistAssignment(BaseModel):
    position: int
    user_id: Optional[int] = None
    notes: Optional[str] = None


class PlaylistImportSaveRequest(BaseModel):
    payload: PlaylistImportResponse
    assignments: List[PlaylistAssignment] = Field(default_factory=list)
    lock_submissions: bool = True


class MonthSettingsRead(ORMModel):
    id: int
    month: datetime
    submission_limit: Optional[int] = None
    spotify_owner_id: Optional[str] = None


class MonthSettingsUpdate(BaseModel):
    submission_limit: Optional[int] = Field(default=None, ge=1)
    spotify_owner_id: Optional[str] = Field(default=None, max_length=120)


class AdminMonthSummary(BaseModel):
    settings: MonthSettingsRead
    submissions: List[SubmissionRead] = Field(default_factory=list)
    released: bool


class ManualReleaseRequest(BaseModel):
    spotify_owner_id: Optional[str] = Field(default=None, max_length=120)


class InviteRead(ORMModel):
    id: int
    token: str
    email: Optional[str]
    role: str
    created_at: datetime
    expires_at: Optional[datetime]
    used_at: Optional[datetime]
    created_by_id: Optional[int]
    used_by_id: Optional[int]


class InviteCreateRequest(BaseModel):
    email: Optional[str] = None
    role: str = "member"
    expires_in_days: int = 7


class InviteListResponse(BaseModel):
    items: List[InviteRead]


class UserRead(ORMModel):
    id: int
    username: str
    display_name: Optional[str]
    role: str
    email: Optional[str]
    spotify_user_id: Optional[str]
    spotify_avatar_url: Optional[str]
    lastfm_username: Optional[str]
    created_at: datetime


class UserListResponse(BaseModel):
    items: List[UserRead]


class SetupStatus(BaseModel):
    ready: bool
    unlocked: bool


class SetupUnlockRequest(BaseModel):
    password: str


class SetupInitializeRequest(BaseModel):
    database_host: str
    database_port: int
    database_name: str
    database_user: str
    database_password: str

    spotify_client_id: str
    spotify_client_secret: str
    spotify_redirect_uri: str
    spotify_scope: str

    secret_key: str
    frontend_redirect_url: Optional[str] = None
    log_level: Optional[str] = None
    enable_scheduler: Optional[bool] = None

    lastfm_api_key: Optional[str] = None
    lastfm_shared_secret: Optional[str] = None
    lastfm_username: Optional[str] = None

    admin_username: str
    admin_display_name: Optional[str] = None
    admin_password: str
    admin_spotify_id: Optional[str] = None
    admin_lastfm_username: Optional[str] = None

    overwrite_env: bool = False


class SetupResponse(BaseModel):
    status: SetupStatus
