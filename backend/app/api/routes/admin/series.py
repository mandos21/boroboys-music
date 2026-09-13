"""Series administration: identity, membership, groups, invites, import."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import delete, or_, select

from app.api.deps import DbSession, get_current_user
from app.api.routes.admin._common import (
    _not_found,
    _require_platform_admin,
    _require_series_admin,
    _require_user,
    _round_summary,
    _series_summary,
    _user_summary,
    router,
)
from app.api.schemas import (
    AdminIdResponse,
    AdminImportedRoundResponse,
    AdminInviteResponse,
    AdminSeriesCreatedResponse,
    AdminSeriesDetailResponse,
    AdminSeriesResponse,
    AdminUserResponse,
)
from app.core.config import get_settings
from app.core.security import hash_secret, new_secret
from app.db.models import (
    ContributorGroup,
    ContributorGroupMember,
    PlatformRole,
    Round,
    Series,
    SeriesAdmin,
    SeriesInvite,
    User,
)
from app.services.membership import ensure_default_series_membership
from app.services.publications import (
    PublicationError,
    import_historical_playlist,
)


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


class InviteCreate(BaseModel):
    expires_in_days: int = Field(default=7, ge=1, le=90)
    role: Literal["contributor", "admin"] = "contributor"
    max_uses: int | None = Field(default=None, ge=1, le=500)


class PlaylistImportRequest(BaseModel):
    publisher_account_id: uuid.UUID
    # Spotify IDs are base62; anything else would be interpolated into a URL path.
    spotify_playlist_id: str = Field(pattern=r"^[A-Za-z0-9]{1,128}$")
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
    ensure_default_series_membership(db, series_id, user_id)
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
