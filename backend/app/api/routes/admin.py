"""Administration endpoints for series, contributor groups, and rounds."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select

from app.api.deps import DbSession, get_current_user, require_csrf
from app.db.models import (
    ContributorGroup,
    ContributorGroupMember,
    PlatformRole,
    Publication,
    PublicationState,
    Round,
    RoundMember,
    RoundStatus,
    Series,
    SeriesAdmin,
    User,
)
from app.services.publications import PublicationError, start_publication, start_unpublish
from app.tasks import publish_round, retire_round

router = APIRouter(prefix="/admin", tags=["administration"], dependencies=[Depends(require_csrf)])


class SeriesCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=100)
    description: str | None = None
    timezone: str = "UTC"
    default_policies: list[dict[str, Any]] = Field(default_factory=list)
    round_plan: dict[str, Any] | None = None
    auto_start_next_round: bool = True

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
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
    policy_snapshot: list[dict[str, Any]] | None = None

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


class PublishRequest(BaseModel):
    publisher_account_id: uuid.UUID


@router.post("/series", status_code=status.HTTP_201_CREATED)
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
    db.commit()
    return {"id": str(series.id), "slug": series.slug}


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
    db.commit()


@router.post("/series/{series_id}/groups", status_code=status.HTTP_201_CREATED)
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


@router.post("/rounds", status_code=status.HTTP_201_CREATED)
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
    round_ = Round(
        series_id=series.id,
        title=payload.title,
        timezone=payload.timezone,
        opens_at=payload.opens_at,
        closes_at=payload.closes_at,
        publish_at=payload.publish_at,
        submission_limit=payload.submission_limit,
        status=RoundStatus.SCHEDULED,
        policy_snapshot=payload.policy_snapshot
        if payload.policy_snapshot is not None
        else series.default_policies,
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
    db.add_all(RoundMember(round_id=round_.id, user_id=member_id) for member_id in member_ids)
    db.commit()
    return {"id": str(round_.id)}


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


@router.post("/rounds/{round_id}/publish", status_code=status.HTTP_202_ACCEPTED)
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
        publication = start_publication(db, round_id, payload.publisher_account_id)
        db.commit()
    except PublicationError as error:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    publish_round.defer(str(publication.id))
    return {"publicationId": str(publication.id), "state": publication.state.value}


@router.post("/rounds/{round_id}/unpublish", status_code=status.HTTP_202_ACCEPTED)
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
    retire_round.defer(str(publication.id))
    return {"publicationId": str(publication.id), "state": publication.state.value}


@router.post("/publications/{publication_id}/retry", status_code=status.HTTP_202_ACCEPTED)
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
        publication.state = PublicationState.PUBLISHING
        round_.status = RoundStatus.PUBLISHING
        db.commit()
        publish_round.defer(str(publication.id))
    elif publication.state is PublicationState.UNPUBLISHING:
        db.commit()
        retire_round.defer(str(publication.id))
    else:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="publication is not retryable"
        )
    return {"publicationId": str(publication.id), "state": publication.state.value}


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
