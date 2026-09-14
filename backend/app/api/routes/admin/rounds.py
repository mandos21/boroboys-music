"""Round administration: scheduling, settings, and contributor membership."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select

from app.api.deps import DbSession, get_current_user
from app.api.routes.admin._common import (
    _not_found,
    _require_publishable_account,
    _require_series_admin,
    _require_user,
    _round_summary,
    _user_summary,
    router,
)
from app.api.schemas import (
    AdminIdResponse,
    AdminRoundDetailResponse,
    AdminRoundResponse,
)
from app.db.models import (
    AuditEvent,
    ContributorGroup,
    ContributorGroupMember,
    Round,
    RoundMember,
    RoundStatus,
    User,
)
from app.services.lifecycle import reconcile_round_status, status_for_timeline


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
    attribution_reveal_delay_seconds: int | None = Field(default=None, ge=0)

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
    attribution_reveal_delay_seconds: int | None = Field(default=None, ge=0)


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
        attribution_reveal_delay_seconds=(
            payload.attribution_reveal_delay_seconds
            if "attribution_reveal_delay_seconds" in payload.model_fields_set
            else series.default_attribution_reveal_delay_seconds
        ),
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
    if "attribution_reveal_delay_seconds" in payload.model_fields_set:
        round_.attribution_reveal_delay_seconds = payload.attribution_reveal_delay_seconds
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
