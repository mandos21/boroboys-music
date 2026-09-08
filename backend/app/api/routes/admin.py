"""Administration endpoints for series, contributor groups, and rounds."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import delete, or_, select

from app.api.deps import DbSession, get_current_user, require_csrf
from app.api.schemas import (
    AdminIdResponse,
    AdminImportedRoundResponse,
    AdminInviteResponse,
    AdminPublicationCommandResponse,
    AdminPublicationResponse,
    AdminRoundDetailResponse,
    AdminRoundResponse,
    AdminSeriesCreatedResponse,
    AdminSeriesDetailResponse,
    AdminSeriesResponse,
    AdminUserResponse,
)
from app.core.config import get_settings
from app.core.security import hash_secret, new_secret
from app.db.models import (
    AuditEvent,
    ContributorGroup,
    ContributorGroupMember,
    ExternalAccount,
    ExternalProvider,
    PlatformRole,
    Publication,
    PublicationState,
    Round,
    RoundMember,
    RoundStatus,
    Series,
    SeriesAdmin,
    SeriesInvite,
    User,
)
from app.services.lifecycle import reconcile_round_status, status_for_timeline
from app.services.membership import ensure_default_series_membership
from app.services.publications import (
    PublicationError,
    defer_or_fail,
    import_historical_playlist,
    start_publication,
    start_unpublish,
)
from app.tasks import defer_publication, defer_retirement

router = APIRouter(prefix="/admin", tags=["administration"], dependencies=[Depends(require_csrf)])


class RollingRoundPlan(BaseModel):
    kind: Literal["rolling"]
    duration_days: int | None = Field(default=None, ge=1, le=365)
    # Preserve existing API-managed hourly plans while the UI moves to days.
    duration_hours: int | None = Field(default=None, ge=1, le=8_760)
    publish_delay_minutes: int = Field(default=0, ge=0, le=43_200)
    submission_limit: int | None = Field(default=None, ge=0)
    title_template: str = Field(default="{previous_title} — next", min_length=1, max_length=200)

    @model_validator(mode="after")
    def has_duration(self) -> RollingRoundPlan:
        if self.duration_days is None and self.duration_hours is None:
            raise ValueError("rolling plan requires duration_days")
        return self


class CalendarRoundPlan(BaseModel):
    """A calendar rule in the series timezone.

    ``full_month`` is the friendly monthly cadence exposed by the application:
    open on the first, close at the end of the month, and release the next day.
    The existing day/duration fields remain for imported and API-managed custom
    calendar rules.
    """

    kind: Literal["calendar"]
    open_day: int = Field(ge=1, le=28)
    duration_days: int = Field(ge=1, le=366)
    full_month: bool = False
    publish_delay_minutes: int = Field(default=0, ge=0, le=43_200)
    submission_limit: int | None = Field(default=None, ge=0)
    title_template: str = Field(default="{year}-{month:02d}", min_length=1, max_length=200)


RoundPlan = Annotated[RollingRoundPlan | CalendarRoundPlan, Field(discriminator="kind")]


class SeriesCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=100)
    description: str | None = None
    timezone: str = "UTC"
    default_policies: list[dict[str, Any]] = Field(default_factory=list)
    round_plan: RoundPlan | None = None
    auto_start_next_round: bool = True
    cover_image_url: str | None = Field(default=None, max_length=1000)
    accent_color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("timezone must be an IANA timezone") from error
        return value


class SeriesUpdate(BaseModel):
    """Mutable series defaults; existing materialized rounds are not rewritten."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    timezone: str | None = None
    default_policies: list[dict[str, Any]] | None = None
    round_plan: RoundPlan | None = None
    auto_start_next_round: bool | None = None
    is_archived: bool | None = None
    cover_image_url: str | None = Field(default=None, max_length=1000)
    accent_color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("timezone must be an IANA timezone") from error
        return value


class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None


class RoundCreate(BaseModel):
    series_id: uuid.UUID
    title: str = Field(min_length=1, max_length=200)
    timezone: str
    opens_at: datetime
    closes_at: datetime
    publish_at: datetime
    submission_limit: int = Field(ge=0)
    contributor_group_ids: list[uuid.UUID] = Field(default_factory=list)
    contributor_user_ids: list[uuid.UUID] = Field(default_factory=list)
    policy_snapshot: list[dict[str, Any]] | None = None
    prompt: str | None = Field(default=None, max_length=2000)
    publisher_account_id: uuid.UUID | None = None

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("timezone must be an IANA timezone") from error
        return value

    @model_validator(mode="after")
    def valid_timeline(self) -> RoundCreate:
        if (
            self.opens_at.tzinfo is None
            or self.closes_at.tzinfo is None
            or self.publish_at.tzinfo is None
        ):
            raise ValueError("round timestamps must include an offset")
        if self.opens_at >= self.closes_at or self.closes_at > self.publish_at:
            raise ValueError("round timeline must satisfy opens < closes <= publish")
        return self


class RoundMemberUpdate(BaseModel):
    submission_limit_override: int | None = Field(default=None, ge=0)


class RoundUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    opens_at: datetime | None = None
    closes_at: datetime | None = None
    publish_at: datetime | None = None
    submission_limit: int | None = Field(default=None, ge=0)
    prompt: str | None = Field(default=None, max_length=2000)
    publisher_account_id: uuid.UUID | None = None


class InviteCreate(BaseModel):
    expires_in_days: int = Field(default=7, ge=1, le=90)
    role: Literal["contributor", "admin"] = "contributor"
    max_uses: int | None = Field(default=None, ge=1, le=500)


class PublishRequest(BaseModel):
    publisher_account_id: uuid.UUID


class PlaylistImportRequest(BaseModel):
    publisher_account_id: uuid.UUID
    spotify_playlist_id: str = Field(min_length=1, max_length=128)
    opens_at: datetime
    closes_at: datetime
    published_at: datetime
    title: str | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def valid_timeline(self) -> PlaylistImportRequest:
        if (
            self.opens_at.tzinfo is None
            or self.closes_at.tzinfo is None
            or self.published_at.tzinfo is None
        ):
            raise ValueError("import timestamps must include an offset")
        if self.opens_at >= self.closes_at or self.closes_at > self.published_at:
            raise ValueError("import timeline must satisfy opens < closes <= published")
        return self


@router.get("/series", response_model=list[AdminSeriesResponse])
def list_series_for_administration(
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> list[dict[str, object]]:
    query = select(Series).order_by(Series.name)
    if user.platform_role is not PlatformRole.ADMIN:
        query = (
            query.join(SeriesAdmin, SeriesAdmin.series_id == Series.id)
            .where(SeriesAdmin.user_id == user.id)
            .distinct()
        )
    return [_series_summary(series) for series in db.scalars(query)]


@router.get("/series/{series_id}", response_model=AdminSeriesDetailResponse)
def get_series_for_administration(
    series_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, object]:
    series = _require_series_admin(db, user, series_id)
    groups = list(
        db.scalars(
            select(ContributorGroup)
            .where(ContributorGroup.series_id == series.id)
            .order_by(ContributorGroup.name)
        )
    )
    rounds = list(
        db.scalars(
            select(Round).where(Round.series_id == series.id).order_by(Round.opens_at.desc())
        )
    )
    members_by_group: dict[uuid.UUID, list[dict[str, object]]] = {group.id: [] for group in groups}
    for group_id, member in db.execute(
        select(ContributorGroupMember.group_id, User)
        .join(User, User.id == ContributorGroupMember.user_id)
        .where(ContributorGroupMember.group_id.in_(members_by_group))
        .order_by(User.display_name, User.email, User.id)
    ):
        members_by_group[group_id].append(_user_summary(member))
    return {
        **_series_summary(series),
        "groups": [
            {
                "id": str(group.id),
                "name": group.name,
                "description": group.description,
                "memberCount": len(members_by_group[group.id]),
                "members": members_by_group[group.id],
            }
            for group in groups
        ],
        "rounds": [_round_summary(round_) for round_ in rounds],
    }


@router.patch("/series/{series_id}", response_model=AdminSeriesResponse)
def update_series(
    series_id: uuid.UUID,
    payload: SeriesUpdate,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, object]:
    """Change future-series defaults without changing existing round snapshots."""
    series = _require_series_admin(db, user, series_id)
    for field in (
        "name",
        "description",
        "timezone",
        "default_policies",
        "round_plan",
        "auto_start_next_round",
        "is_archived",
        "cover_image_url",
        "accent_color",
    ):
        if field not in payload.model_fields_set:
            continue
        value = getattr(payload, field)
        if field == "round_plan" and value is not None:
            value = value.model_dump()
        setattr(series, field, value)
    db.commit()
    return _series_summary(series)


@router.get("/series/{series_id}/users", response_model=list[AdminUserResponse])
def search_users_for_series(
    series_id: uuid.UUID,
    query: Annotated[str, Query(min_length=2, max_length=100)],
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> list[dict[str, object]]:
    _require_series_admin(db, user, series_id)
    # Escape the wildcards so a query of "%" searches for a literal percent
    # sign rather than listing every provisioned account.
    escaped = query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    users = db.scalars(
        select(User)
        .where(
            User.is_active.is_(True),
            or_(
                User.email.ilike(pattern, escape="\\"),
                User.display_name.ilike(pattern, escape="\\"),
            ),
        )
        .order_by(User.display_name, User.email, User.id)
        .limit(20)
    )
    return [_user_summary(candidate) for candidate in users]


@router.get("/series/{series_id}/members", response_model=list[AdminUserResponse])
def list_series_members(
    series_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> list[dict[str, object]]:
    """Expose the union of configured contributor groups as a simple member list."""
    _require_series_admin(db, user, series_id)
    members = db.scalars(
        select(User)
        .join(ContributorGroupMember, ContributorGroupMember.user_id == User.id)
        .join(ContributorGroup, ContributorGroup.id == ContributorGroupMember.group_id)
        .where(ContributorGroup.series_id == series_id)
        .distinct()
        .order_by(User.display_name, User.email, User.id)
    )
    return [_user_summary(member) for member in members]


@router.put(
    "/series/{series_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
def add_series_member(
    series_id: uuid.UUID,
    user_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> None:
    """Add a member through the default group while retaining group support internally."""
    _require_series_admin(db, user, series_id)
    _require_user(db, user_id)
    group = db.scalar(
        select(ContributorGroup).where(
            ContributorGroup.series_id == series_id,
            ContributorGroup.name == "Series members",
        )
    )
    if group is None:
        group = ContributorGroup(series_id=series_id, name="Series members")
        db.add(group)
        db.flush()
    existing = db.scalar(
        select(ContributorGroupMember).where(
            ContributorGroupMember.group_id == group.id,
            ContributorGroupMember.user_id == user_id,
        )
    )
    if existing is None:
        db.add(ContributorGroupMember(group_id=group.id, user_id=user_id))
        db.commit()


@router.delete(
    "/series/{series_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
def remove_series_member(
    series_id: uuid.UUID,
    user_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> None:
    _require_series_admin(db, user, series_id)
    group_ids = select(ContributorGroup.id).where(ContributorGroup.series_id == series_id)
    db.execute(
        delete(ContributorGroupMember).where(
            ContributorGroupMember.group_id.in_(group_ids),
            ContributorGroupMember.user_id == user_id,
        )
    )
    db.commit()


@router.post(
    "/series",
    status_code=status.HTTP_201_CREATED,
    response_model=AdminSeriesCreatedResponse,
)
def create_series(
    payload: SeriesCreate,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, str]:
    _require_platform_admin(user)
    series = Series(**payload.model_dump())
    db.add(series)
    db.flush()
    db.add(SeriesAdmin(series_id=series.id, user_id=user.id))
    ensure_default_series_membership(db, series.id, user.id)
    db.commit()
    return {"id": str(series.id), "slug": series.slug}


@router.post(
    "/series/{series_id}/invites",
    status_code=status.HTTP_201_CREATED,
    response_model=AdminInviteResponse,
)
def create_series_invite(
    series_id: uuid.UUID,
    payload: InviteCreate,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, object]:
    _require_series_admin(db, user, series_id)
    token = new_secret()
    invite = SeriesInvite(
        series_id=series_id,
        created_by_id=user.id,
        token_hash=hash_secret(token),
        role=payload.role,
        expires_at=datetime.now(UTC) + timedelta(days=payload.expires_in_days),
        max_uses=payload.max_uses,
    )
    db.add(invite)
    db.commit()
    return {
        "id": str(invite.id),
        "url": f"{str(get_settings().app_base_url).rstrip('/')}/invites/{token}",
        "expiresAt": invite.expires_at.isoformat(),
        "role": invite.role,
        "maxUses": invite.max_uses,
    }


@router.post(
    "/series/{series_id}/import-spotify-playlist",
    status_code=status.HTTP_201_CREATED,
    response_model=AdminImportedRoundResponse,
)
def import_spotify_playlist(
    series_id: uuid.UUID,
    payload: PlaylistImportRequest,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, str]:
    _require_series_admin(db, user, series_id)
    try:
        round_ = import_historical_playlist(
            db,
            series_id=series_id,
            publisher_account_id=payload.publisher_account_id,
            spotify_playlist_id=payload.spotify_playlist_id,
            opens_at=payload.opens_at,
            closes_at=payload.closes_at,
            published_at=payload.published_at,
            actor_id=user.id,
            title=payload.title,
        )
        db.commit()
    except PublicationError as error:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return {"roundId": str(round_.id)}


@router.post(
    "/series/{series_id}/admins/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
def add_series_admin(
    series_id: uuid.UUID,
    user_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> None:
    _require_series_admin(db, user, series_id)
    _require_user(db, user_id)
    if db.scalar(
        select(SeriesAdmin).where(
            SeriesAdmin.series_id == series_id, SeriesAdmin.user_id == user_id
        )
    ):
        return
    db.add(SeriesAdmin(series_id=series_id, user_id=user_id))
    ensure_default_series_membership(db, series_id, user_id)
    db.commit()


@router.post(
    "/series/{series_id}/groups",
    status_code=status.HTTP_201_CREATED,
    response_model=AdminIdResponse,
)
def create_group(
    series_id: uuid.UUID,
    payload: GroupCreate,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, str]:
    _require_series_admin(db, user, series_id)
    group = ContributorGroup(series_id=series_id, **payload.model_dump())
    db.add(group)
    db.commit()
    return {"id": str(group.id)}


@router.put(
    "/groups/{group_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
def add_group_member(
    group_id: uuid.UUID,
    user_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> None:
    group = db.get(ContributorGroup, group_id)
    if group is None:
        raise _not_found("contributor group")
    _require_series_admin(db, user, group.series_id)
    _require_user(db, user_id)
    existing = db.scalar(
        select(ContributorGroupMember).where(
            ContributorGroupMember.group_id == group_id, ContributorGroupMember.user_id == user_id
        )
    )
    if existing is None:
        db.add(ContributorGroupMember(group_id=group_id, user_id=user_id))
        db.commit()


@router.post("/rounds", status_code=status.HTTP_201_CREATED, response_model=AdminIdResponse)
def create_round(
    payload: RoundCreate,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, str]:
    series = _require_series_admin(db, user, payload.series_id)
    groups = list(
        db.scalars(
            select(ContributorGroup).where(
                ContributorGroup.id.in_(payload.contributor_group_ids),
                ContributorGroup.series_id == series.id,
            )
        )
    )
    if len(groups) != len(set(payload.contributor_group_ids)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid group"
        )
    if payload.publisher_account_id is not None:
        _require_publishable_account(db, series.id, payload.publisher_account_id)
    round_ = Round(
        series_id=series.id,
        title=payload.title,
        timezone=payload.timezone,
        opens_at=payload.opens_at,
        closes_at=payload.closes_at,
        publish_at=payload.publish_at,
        submission_limit=payload.submission_limit,
        status=status_for_timeline(payload.opens_at, payload.closes_at),
        policy_snapshot=payload.policy_snapshot
        if payload.policy_snapshot is not None
        else series.default_policies,
        prompt=payload.prompt,
        publisher_account_id=payload.publisher_account_id,
    )
    db.add(round_)
    db.flush()
    member_ids = set(
        db.scalars(
            select(ContributorGroupMember.user_id).where(
                ContributorGroupMember.group_id.in_([group.id for group in groups])
            )
        )
    )
    requested_members = set(payload.contributor_user_ids)
    if requested_members:
        valid_members = set(
            db.scalars(
                select(User.id).where(User.id.in_(requested_members), User.is_active.is_(True))
            )
        )
        if valid_members != requested_members:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid user"
            )
        member_ids.update(requested_members)
    db.add_all(RoundMember(round_id=round_.id, user_id=member_id) for member_id in member_ids)
    db.commit()
    return {"id": str(round_.id)}


@router.patch("/rounds/{round_id}", response_model=AdminRoundResponse)
def update_round(
    round_id: uuid.UUID,
    payload: RoundUpdate,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, object]:
    round_ = db.get(Round, round_id)
    if round_ is None:
        raise _not_found("round")
    _require_series_admin(db, user, round_.series_id)
    if round_.status not in {RoundStatus.DRAFT, RoundStatus.SCHEDULED, RoundStatus.OPEN}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="round schedule is frozen")
    if round_.status is RoundStatus.OPEN and "opens_at" in payload.model_fields_set:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="an open round's opening time cannot be changed",
        )
    opens_at = payload.opens_at or round_.opens_at
    closes_at = payload.closes_at or round_.closes_at
    publish_at = payload.publish_at or round_.publish_at
    if any(value.tzinfo is None for value in (opens_at, closes_at, publish_at)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="round timestamps must include an offset",
        )
    if opens_at >= closes_at or closes_at > publish_at:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="round timeline must satisfy opens < closes <= publish",
        )
    if payload.title is not None:
        round_.title = payload.title
    if payload.submission_limit is not None:
        round_.submission_limit = payload.submission_limit
    if "prompt" in payload.model_fields_set:
        round_.prompt = payload.prompt
    if "publisher_account_id" in payload.model_fields_set:
        if payload.publisher_account_id is not None:
            _require_publishable_account(db, round_.series_id, payload.publisher_account_id)
        round_.publisher_account_id = payload.publisher_account_id
    round_.opens_at, round_.closes_at, round_.publish_at = opens_at, closes_at, publish_at
    round_.status = status_for_timeline(opens_at, closes_at)
    db.commit()
    return _round_summary(round_)


@router.get("/rounds/{round_id}", response_model=AdminRoundDetailResponse)
def get_round_for_administration(
    round_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, object]:
    round_ = db.get(Round, round_id)
    if round_ is None:
        raise _not_found("round")
    _require_series_admin(db, user, round_.series_id)
    if reconcile_round_status(round_):
        db.commit()
    members = list(
        db.execute(
            select(RoundMember, User)
            .join(User, User.id == RoundMember.user_id)
            .where(RoundMember.round_id == round_.id)
            .order_by(RoundMember.removed_at.is_not(None), User.display_name, User.email, User.id)
        )
    )
    return {
        **_round_summary(round_),
        "seriesId": str(round_.series_id),
        "timezone": round_.timezone,
        "policySnapshot": round_.policy_snapshot,
        "members": [
            {
                **_user_summary(member_user),
                "submissionLimitOverride": membership.submission_limit_override,
                "removedAt": membership.removed_at.isoformat() if membership.removed_at else None,
            }
            for membership, member_user in members
        ],
    }


@router.get("/rounds/{round_id}/publication", response_model=AdminPublicationResponse | None)
def get_publication_status(
    round_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, object] | None:
    """Expose durable publication progress and its audit trail to a series admin."""
    round_ = db.get(Round, round_id)
    if round_ is None:
        raise _not_found("round")
    _require_series_admin(db, user, round_.series_id)
    publication = db.scalar(select(Publication).where(Publication.round_id == round_id))
    if publication is None:
        return None
    events = list(
        db.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.target_type == "publication",
                AuditEvent.target_id == publication.id,
            )
            .order_by(AuditEvent.created_at.desc())
        )
    )
    return {
        "id": str(publication.id),
        "state": publication.state.value,
        "isImported": publication.is_imported,
        "retirementRequested": publication.retirement_requested,
        "spotifyPlaylistId": publication.spotify_playlist_id,
        "attemptCount": publication.attempt_count,
        "lastError": publication.last_error,
        "publishedAt": publication.published_at.isoformat() if publication.published_at else None,
        "unpublishedAt": publication.unpublished_at.isoformat()
        if publication.unpublished_at
        else None,
        "events": [
            {
                "id": str(event.id),
                "action": event.action,
                "createdAt": event.created_at.isoformat(),
            }
            for event in events
        ],
    }


@router.put(
    "/rounds/{round_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
def add_round_member(
    round_id: uuid.UUID,
    user_id: uuid.UUID,
    payload: RoundMemberUpdate,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> None:
    round_ = db.get(Round, round_id)
    if round_ is None:
        raise _not_found("round")
    _require_series_admin(db, user, round_.series_id)
    if round_.status not in {RoundStatus.DRAFT, RoundStatus.SCHEDULED, RoundStatus.OPEN}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="round membership is frozen"
        )
    _require_user(db, user_id)
    membership = db.scalar(
        select(RoundMember).where(RoundMember.round_id == round_id, RoundMember.user_id == user_id)
    )
    if membership is None:
        db.add(
            RoundMember(
                round_id=round_id,
                user_id=user_id,
                submission_limit_override=payload.submission_limit_override,
            )
        )
    else:
        membership.submission_limit_override = payload.submission_limit_override
        membership.removed_at = None
    db.commit()


@router.delete(
    "/rounds/{round_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
def remove_round_member(
    round_id: uuid.UUID,
    user_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> None:
    round_ = db.get(Round, round_id)
    if round_ is None:
        raise _not_found("round")
    _require_series_admin(db, user, round_.series_id)
    if round_.status not in {RoundStatus.DRAFT, RoundStatus.SCHEDULED, RoundStatus.OPEN}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="round membership is frozen"
        )
    membership = db.scalar(
        select(RoundMember).where(RoundMember.round_id == round_id, RoundMember.user_id == user_id)
    )
    if membership is None or membership.removed_at is not None:
        return
    membership.removed_at = datetime.now(UTC)
    db.add(
        AuditEvent(
            actor_id=user.id,
            action="round_member.removed",
            target_type="round_member",
            target_id=membership.id,
            details={"roundId": str(round_id), "userId": str(user_id)},
        )
    )
    db.commit()


@router.post(
    "/rounds/{round_id}/publish",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AdminPublicationCommandResponse,
)
def publish_round_request(
    round_id: uuid.UUID,
    payload: PublishRequest,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, str]:
    round_ = db.get(Round, round_id)
    if round_ is None:
        raise _not_found("round")
    _require_series_admin(db, user, round_.series_id)
    try:
        publication = start_publication(db, round_id, payload.publisher_account_id, user.id)
        db.commit()
    except PublicationError as error:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    defer_or_fail(db, publication, round_, defer_publication)
    return {"publicationId": str(publication.id), "state": publication.state.value}


@router.post(
    "/rounds/{round_id}/unpublish",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AdminPublicationCommandResponse,
)
def unpublish_round_request(
    round_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, str]:
    round_ = db.get(Round, round_id)
    if round_ is None:
        raise _not_found("round")
    _require_series_admin(db, user, round_.series_id)
    try:
        publication = start_unpublish(db, round_id)
        db.commit()
    except PublicationError as error:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    defer_or_fail(db, publication, round_, defer_retirement)
    return {"publicationId": str(publication.id), "state": publication.state.value}


@router.post(
    "/publications/{publication_id}/retry",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AdminPublicationCommandResponse,
)
def retry_publication(
    publication_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, str]:
    publication = db.get(Publication, publication_id)
    if publication is None:
        raise _not_found("publication")
    round_ = db.get(Round, publication.round_id)
    if round_ is None:
        raise _not_found("round")
    _require_series_admin(db, user, round_.series_id)
    if publication.state is PublicationState.FAILED:
        if publication.retirement_requested:
            publication.state = PublicationState.UNPUBLISHING
            round_.status = RoundStatus.UNPUBLISHING
            defer = defer_retirement
        else:
            publication.state = PublicationState.PUBLISHING
            round_.status = RoundStatus.PUBLISHING
            defer = defer_publication
        # The previous failure is no longer the current state of this
        # publication, so it must not keep being reported as one.
        publication.last_error = None
        db.commit()
        defer_or_fail(db, publication, round_, defer)
    else:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="publication is not retryable"
        )
    return {"publicationId": str(publication.id), "state": publication.state.value}


def _require_publishable_account(
    db: DbSession, series_id: uuid.UUID, account_id: uuid.UUID
) -> ExternalAccount:
    """Accept a scheduled publisher only if a series administrator owns it.

    A round publishes to this account without anyone present, so the account
    must belong to somebody who could have published the round by hand.
    """
    account = db.get(ExternalAccount, account_id)
    if account is None or account.provider is not ExternalProvider.SPOTIFY or not account.is_active:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="a connected Spotify account is required to publish automatically",
        )
    owner = db.get(User, account.user_id)
    is_series_admin = owner is not None and (
        owner.platform_role is PlatformRole.ADMIN
        or db.scalar(
            select(SeriesAdmin.id).where(
                SeriesAdmin.series_id == series_id, SeriesAdmin.user_id == account.user_id
            )
        )
        is not None
    )
    if not is_series_admin:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="the publishing account must belong to a series administrator",
        )
    return account


def _require_platform_admin(user: User) -> None:
    if user.platform_role is not PlatformRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="platform admin required")


def _require_series_admin(db: DbSession, user: User, series_id: uuid.UUID) -> Series:
    series = db.get(Series, series_id)
    if series is None:
        raise _not_found("series")
    if user.platform_role is PlatformRole.ADMIN:
        return series
    assigned = db.scalar(
        select(SeriesAdmin.id).where(
            SeriesAdmin.series_id == series_id, SeriesAdmin.user_id == user.id
        )
    )
    if assigned is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="series admin required")
    return series


def _require_user(db: DbSession, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise _not_found("user")
    return user


def _not_found(resource: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{resource} not found")


def _series_summary(series: Series) -> dict[str, object]:
    return {
        "id": str(series.id),
        "name": series.name,
        "slug": series.slug,
        "description": series.description,
        "timezone": series.timezone,
        "defaultPolicies": series.default_policies,
        "roundPlan": series.round_plan,
        "autoStartNextRound": series.auto_start_next_round,
        "isArchived": series.is_archived,
        "coverImageUrl": series.cover_image_url,
        "accentColor": series.accent_color,
    }


def _round_summary(round_: Round) -> dict[str, object]:
    return {
        "id": str(round_.id),
        "title": round_.title,
        "status": round_.status.value,
        "opensAt": round_.opens_at.isoformat(),
        "closesAt": round_.closes_at.isoformat(),
        "publishAt": round_.publish_at.isoformat(),
        "submissionLimit": round_.submission_limit,
        "prompt": round_.prompt,
        "publisherAccountId": str(round_.publisher_account_id)
        if round_.publisher_account_id
        else None,
    }


def _user_summary(user: User) -> dict[str, object]:
    return {
        "id": str(user.id),
        "displayName": user.display_name,
        "email": user.email,
    }
