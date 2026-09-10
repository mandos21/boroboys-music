"""Explicit, camel-case response contracts shared with the web client.

Input models stay next to the routes that own their validation.  These output
models deliberately live in one small module so OpenAPI documents the values
the browser may rely on without coupling route implementations to ORM models.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def _camel_case(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class ApiResponse(BaseModel):
    model_config = ConfigDict(alias_generator=_camel_case, populate_by_name=True)


class SessionUserResponse(ApiResponse):
    id: str
    email: str | None
    display_name: str | None
    platform_role: str


class SessionResponse(ApiResponse):
    user: SessionUserResponse
    expires_at: datetime
    csrf_cookie_name: str


class ConnectionResponse(ApiResponse):
    id: str
    provider: str
    display_name: str | None
    profile_image_url: str | None
    visibility: str
    is_active: bool
    disconnected_at: datetime | None


class RoundListResponse(ApiResponse):
    id: str
    series_id: str
    title: str
    status: str
    opens_at: datetime
    closes_at: datetime
    publish_at: datetime
    submission_limit: int


class RoundPreviewResponse(ApiResponse):
    id: str
    title: str
    status: str
    opens_at: datetime
    closes_at: datetime
    publish_at: datetime
    submitted_count: int
    contributor_count: int
    prompt: str | None


class RoundDetailResponse(RoundPreviewResponse):
    series_id: str
    submission_limit: int
    spotify_playlist_url: str | None
    can_manage: bool
    background_artwork_url: str | None
    artwork_urls: list[str]


class TrackResponse(ApiResponse):
    spotify_track_id: str
    name: str
    artist: str
    album: str | None
    spotify_uri: str | None
    artwork_url: str | None
    provider_metadata: dict[str, Any] = Field(default_factory=dict)


class ContributorResponse(ApiResponse):
    id: str
    display_name: str
    spotify_profile_image_url: str | None


class SubmissionResponse(ApiResponse):
    id: str
    status: str
    note: str | None
    created_at: datetime
    updated_at: datetime
    withdrawn_at: datetime | None
    is_mine: bool
    contributor: ContributorResponse
    track: TrackResponse


class ProfileStatItemResponse(ApiResponse):
    name: str
    count: int


class ProfileGenreItemResponse(ProfileStatItemResponse):
    """A genre plus the family group it belongs to, so the client can colour
    related genres alike instead of by their rank in the list."""

    group: str


class ProfileAffinityResponse(ApiResponse):
    """One other listener, and how much of this profile's taste they share."""

    id: str
    display_name: str
    spotify_profile_image_url: str | None
    affinity: int
    shared_genres: list[str]
    shared_round_count: int


class ProfileSubmissionResponse(ApiResponse):
    id: str
    submitted_at: datetime
    note: str | None
    track: TrackResponse
    series_id: str
    series_name: str
    round_id: str
    round_title: str


class ProfileStatsResponse(ApiResponse):
    submission_count: int
    unique_track_count: int
    unique_artist_count: int
    unique_album_count: int
    unique_genre_count: int
    genre_tagged_track_count: int
    diversity_score: int
    top_artists: list[ProfileStatItemResponse]
    genre_spread: list[ProfileGenreItemResponse]
    affinity: list[ProfileAffinityResponse]


class ProfileResponse(ApiResponse):
    id: str
    display_name: str
    spotify_profile_image_url: str | None
    is_me: bool
    stats: ProfileStatsResponse
    submissions: list[ProfileSubmissionResponse]
    history_count: int
    next_cursor: str | None


class SubmissionDraftResponse(ApiResponse):
    # Drafts are intentionally stored in the same provider-shaped form that
    # the submission input accepts. Track metadata becomes trusted only when
    # it is evaluated or submitted, so it is not a TrackResponse.
    track: dict[str, Any] | None
    note: str | None


class PolicyResultResponse(ApiResponse):
    kind: str
    version: str
    decision: str
    message: str
    result: dict[str, Any]


class TrackEvaluationResponse(ApiResponse):
    track_id: str
    can_submit: bool
    limit_remaining: int
    requires_warning_confirmation: bool
    policy_results: list[PolicyResultResponse]


class SubmissionResultResponse(ApiResponse):
    accepted: bool
    id: str | None = None
    requires_warning_confirmation: bool | None = None
    policy_results: list[PolicyResultResponse]


class EvidenceItemResponse(ApiResponse):
    account_id: str
    display_name: str | None
    is_mine: bool
    playcount: int | None
    artist_playcount: int | None
    album_playcount: int | None
    fetched_at: datetime
    refresh_after: datetime | None
    status: str


class EvidenceResponse(ApiResponse):
    round_id: str
    track_id: str
    evidence: list[EvidenceItemResponse]


class SeriesContributorResponse(ContributorResponse):
    """A contributor plus the genre mix they bring to the series."""

    track_count: int
    genres: list[ProfileGenreItemResponse]


class SeriesSummaryStatsResponse(ApiResponse):
    """The small, immediately useful portion of a series overview."""

    round_count: int
    song_count: int
    artist_count: int
    contributors: list[ContributorResponse]


class SeriesGenreInsightsResponse(ApiResponse):
    """Genre detail fetched independently of the series history shell."""

    genre_tagged_track_count: int
    unique_track_count: int
    genre_spread: list[ProfileGenreItemResponse]
    contributors: list[SeriesContributorResponse]


class SeriesHistoryRoundResponse(ApiResponse):
    id: str
    title: str
    status: str
    opens_at: datetime
    closes_at: datetime
    publish_at: datetime
    prompt: str | None
    artwork_urls: list[str]


class SeriesHistoryResponse(ApiResponse):
    id: str
    name: str
    description: str | None
    timezone: str
    cover_image_url: str | None
    accent_color: str | None
    fallback_artwork_url: str | None
    is_admin: bool
    stats: SeriesSummaryStatsResponse
    rounds: list[SeriesHistoryRoundResponse]


class SeriesListResponse(ApiResponse):
    id: str
    name: str
    description: str | None
    timezone: str
    cover_image_url: str | None
    accent_color: str | None
    fallback_artwork_url: str | None
    is_admin: bool
    featured_round: RoundPreviewResponse | None


class AdminUserResponse(ApiResponse):
    id: str
    display_name: str | None
    email: str | None


class AdminSeriesResponse(ApiResponse):
    id: str
    name: str
    slug: str
    description: str | None
    timezone: str
    default_policies: list[dict[str, Any]]
    round_plan: dict[str, Any] | None
    auto_start_next_round: bool
    is_archived: bool
    cover_image_url: str | None
    accent_color: str | None


class AdminGroupResponse(ApiResponse):
    id: str
    name: str
    description: str | None
    member_count: int
    members: list[AdminUserResponse]


class AdminRoundResponse(ApiResponse):
    id: str
    title: str
    status: str
    opens_at: datetime
    closes_at: datetime
    publish_at: datetime
    submission_limit: int
    prompt: str | None
    publisher_account_id: str | None


class AdminSeriesDetailResponse(AdminSeriesResponse):
    groups: list[AdminGroupResponse]
    rounds: list[AdminRoundResponse]


class AdminRoundMemberResponse(AdminUserResponse):
    submission_limit_override: int | None
    removed_at: datetime | None


class AdminRoundDetailResponse(AdminRoundResponse):
    series_id: str
    timezone: str
    policy_snapshot: list[dict[str, Any]]
    members: list[AdminRoundMemberResponse]


class AdminPublicationEventResponse(ApiResponse):
    id: str
    action: str
    created_at: datetime


class AdminPublicationResponse(ApiResponse):
    id: str
    state: str
    is_imported: bool
    retirement_requested: bool
    spotify_playlist_id: str | None
    attempt_count: int
    last_error: str | None
    published_at: datetime | None
    unpublished_at: datetime | None
    events: list[AdminPublicationEventResponse]


class AdminPublicationCommandResponse(ApiResponse):
    publication_id: str
    state: str


class AdminSeriesCreatedResponse(ApiResponse):
    id: str
    slug: str


class AdminInviteResponse(ApiResponse):
    id: str
    url: str
    expires_at: datetime
    role: str
    max_uses: int | None


class AdminIdResponse(ApiResponse):
    id: str


class AdminImportedRoundResponse(ApiResponse):
    round_id: str
