"""Contributor-visible series history without leaking other private round groups."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select

from app.api.deps import DbSession, get_current_user, require_csrf
from app.core.security import hash_secret
from app.db.models import (
    ContributorGroup,
    ContributorGroupMember,
    ExternalAccount,
    ExternalProvider,
    PlatformRole,
    Round,
    RoundMember,
    Series,
    SeriesAdmin,
    SeriesInvite,
    Submission,
    SubmissionStatus,
    Track,
    User,
)
from app.services.lifecycle import reconcile_round_status
from app.services.membership import ensure_default_series_membership

router = APIRouter(prefix="/series", tags=["series"])


@router.post("/invites/{token}/accept", dependencies=[Depends(require_csrf)])
def accept_series_invite(
    token: str,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, object]:
    invite = db.scalar(
        select(SeriesInvite)
        .where(SeriesInvite.token_hash == hash_secret(token))
        .with_for_update()
    )
    already_member = invite is not None and _has_series_membership(db, invite.series_id, user.id)
    if (
        invite is None
        or invite.revoked_at is not None
        or invite.expires_at <= datetime.now(UTC)
        or (
            not already_member
            and invite.max_uses is not None
            and invite.use_count >= invite.max_uses
        )
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="invite is unavailable")
    ensure_default_series_membership(db, invite.series_id, user.id)
    if invite.role == "admin" and not db.scalar(
        select(SeriesAdmin.id).where(
            SeriesAdmin.series_id == invite.series_id,
            SeriesAdmin.user_id == user.id,
        )
    ):
        db.add(SeriesAdmin(series_id=invite.series_id, user_id=user.id))
    if not already_member:
        invite.use_count += 1
    db.commit()
    return {"seriesId": str(invite.series_id), "role": invite.role}


@router.get("")
def list_my_series(
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> list[dict[str, object]]:
    """List every series a listener can enter, with a useful round preview."""
    if user.platform_role is PlatformRole.ADMIN:
        series_items = list(db.scalars(select(Series).order_by(Series.name)))
    else:
        series_items = list(
            db.scalars(
                select(Series)
                .outerjoin(Round, Round.series_id == Series.id)
                .outerjoin(
                    RoundMember,
                    (RoundMember.round_id == Round.id)
                    & (RoundMember.user_id == user.id)
                    & RoundMember.removed_at.is_(None),
                )
                .outerjoin(
                    SeriesAdmin,
                    (SeriesAdmin.series_id == Series.id) & (SeriesAdmin.user_id == user.id),
                )
                .outerjoin(ContributorGroup, ContributorGroup.series_id == Series.id)
                .outerjoin(
                    ContributorGroupMember,
                    (ContributorGroupMember.group_id == ContributorGroup.id)
                    & (ContributorGroupMember.user_id == user.id),
                )
                .where(
                    or_(
                        RoundMember.id.is_not(None),
                        SeriesAdmin.id.is_not(None),
                        ContributorGroupMember.id.is_not(None),
                    )
                )
                .distinct()
                .order_by(Series.name)
            )
        )
    payloads = [_series_payload(db, series, user) for series in series_items]
    return sorted(payloads, key=_series_sort_key)


@router.get("/{series_id}")
def get_series_history(
    series_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, object]:
    """Return rounds visible to the caller within one series.

    Series may run overlapping contributor groups. A normal contributor sees
    only their active materialized memberships; platform and series admins can
    inspect the complete series history.
    """
    series = db.get(Series, series_id)
    if series is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="series not found")
    is_admin = _is_series_admin(db, series_id, user)
    rounds = _visible_rounds(db, series_id, user, is_admin)
    if not is_admin and not rounds and not _has_series_membership(db, series_id, user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="series access required")
    stats = _series_stats(db, rounds)
    fallback_artwork_url = _fallback_artwork_url(db, rounds) if not series.cover_image_url and not series.accent_color else None
    return {
        "id": str(series.id),
        "name": series.name,
        "description": series.description,
        "timezone": series.timezone,
        "coverImageUrl": series.cover_image_url,
        "accentColor": series.accent_color,
        "fallbackArtworkUrl": fallback_artwork_url,
        "isAdmin": is_admin,
        "stats": stats,
        "rounds": [
            {
                "id": str(round_.id),
                "title": round_.title,
                "status": round_.status.value,
                "opensAt": round_.opens_at.isoformat(),
                "closesAt": round_.closes_at.isoformat(),
                "publishAt": round_.publish_at.isoformat(),
                "prompt": round_.prompt,
                "artworkUrls": _round_artwork_urls(db, round_.id),
            }
            for round_ in rounds
        ],
    }


def _series_payload(db: DbSession, series: Series, user: User) -> dict[str, object]:
    is_admin = _is_series_admin(db, series.id, user)
    rounds = _visible_rounds(db, series.id, user, is_admin)
    active = next((round_ for round_ in rounds if round_.status.value == "open"), None)
    active = active or next(
        (round_ for round_ in rounds if round_.status.value != "published"), None
    )
    latest = active or (rounds[0] if rounds else None)
    fallback_artwork_url = _fallback_artwork_url(db, [latest]) if latest and not series.cover_image_url and not series.accent_color else None
    return {
        "id": str(series.id),
        "name": series.name,
        "description": series.description,
        "timezone": series.timezone,
        "coverImageUrl": series.cover_image_url,
        "accentColor": series.accent_color,
        "fallbackArtworkUrl": fallback_artwork_url,
        "isAdmin": is_admin,
        "featuredRound": _round_payload(db, latest) if latest else None,
    }


def _series_sort_key(item: dict[str, object]) -> tuple[bool, str]:
    featured = item["featuredRound"]
    is_open = isinstance(featured, dict) and featured.get("status") == "open"
    return (not is_open, str(item["name"]).lower())


def _visible_rounds(db: DbSession, series_id: uuid.UUID, user: User, is_admin: bool) -> list[Round]:
    statement = select(Round).where(Round.series_id == series_id)
    if not is_admin:
        statement = (
            statement.join(RoundMember, RoundMember.round_id == Round.id)
            .where(RoundMember.user_id == user.id, RoundMember.removed_at.is_(None))
            .distinct()
        )
    rounds = list(db.scalars(statement.order_by(Round.opens_at.desc())))
    if any(reconcile_round_status(round_) for round_ in rounds):
        db.commit()
    return sorted(
        rounds,
        key=lambda round_: (
            0
            if round_.status.value == "open"
            else 1
            if round_.status.value != "published"
            else 2,
            -round_.opens_at.timestamp(),
        ),
    )


def _is_series_admin(db: DbSession, series_id: uuid.UUID, user: User) -> bool:
    return user.platform_role is PlatformRole.ADMIN or (
        db.scalar(
            select(SeriesAdmin.id).where(
                SeriesAdmin.series_id == series_id,
                SeriesAdmin.user_id == user.id,
            )
        )
        is not None
    )


def _has_series_membership(db: DbSession, series_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(ContributorGroupMember.group_id)
            .join(ContributorGroup, ContributorGroup.id == ContributorGroupMember.group_id)
            .where(
                ContributorGroup.series_id == series_id,
                ContributorGroupMember.user_id == user_id,
            )
        )
        is not None
    )


def _round_payload(db: DbSession, round_: Round) -> dict[str, object]:
    submitted_count = int(
        db.scalar(
            select(func.count(func.distinct(Submission.contributor_id))).where(
                Submission.round_id == round_.id,
                Submission.status == SubmissionStatus.ACCEPTED,
            )
        )
        or 0
    )
    contributor_count = int(
        db.scalar(
            select(func.count())
            .select_from(RoundMember)
            .where(RoundMember.round_id == round_.id, RoundMember.removed_at.is_(None))
        )
        or 0
    )
    return {
        "id": str(round_.id),
        "title": round_.title,
        "status": round_.status.value,
        "opensAt": round_.opens_at.isoformat(),
        "closesAt": round_.closes_at.isoformat(),
        "publishAt": round_.publish_at.isoformat(),
        "submittedCount": submitted_count,
        "contributorCount": contributor_count,
        "prompt": round_.prompt,
    }


def _round_artwork_urls(db: DbSession, round_id: uuid.UUID, limit: int = 8) -> list[str]:
    """Pick artwork round-robin so a prolific contributor cannot fill a collage."""
    rows = list(
        db.execute(
            select(Submission.contributor_id, Track.artwork_url)
            .join(Track, Track.id == Submission.track_id)
            .where(
                Submission.round_id == round_id,
                Submission.status == SubmissionStatus.ACCEPTED,
                Track.artwork_url.is_not(None),
            )
            .order_by(Submission.created_at, Submission.id)
        )
    )
    by_contributor: dict[uuid.UUID, list[str]] = {}
    for contributor_id, artwork_url in rows:
        if isinstance(artwork_url, str):
            by_contributor.setdefault(contributor_id, []).append(artwork_url)
    selected: list[str] = []
    while by_contributor and len(selected) < limit:
        for contributor_id in list(by_contributor):
            selected.append(by_contributor[contributor_id].pop(0))
            if not by_contributor[contributor_id]:
                del by_contributor[contributor_id]
            if len(selected) == limit:
                break
    return selected


def _fallback_artwork_url(db: DbSession, rounds: Sequence[Round | None]) -> str | None:
    for round_ in rounds:
        if round_ is None:
            continue
        artwork_urls = _round_artwork_urls(db, round_.id)
        if artwork_urls:
            # A rotating offset keeps a no-theme series visually musical without
            # persisting a separate identity just for its first release.
            return artwork_urls[round_.id.int % len(artwork_urls)]
    return None


def _series_stats(db: DbSession, rounds: list[Round]) -> dict[str, object]:
    if not rounds:
        return {"roundCount": 0, "songCount": 0, "artistCount": 0, "contributors": []}
    round_ids = [round_.id for round_ in rounds]
    spotify_profile_image = (
        select(ExternalAccount.profile_image_url)
        .where(
            ExternalAccount.user_id == User.id,
            ExternalAccount.provider == ExternalProvider.SPOTIFY,
            ExternalAccount.is_active.is_(True),
        )
        .order_by(ExternalAccount.created_at)
        .limit(1)
        .scalar_subquery()
    )
    rows = list(
        db.execute(
            select(User.id, User.display_name, User.email, spotify_profile_image, Track.artist)
            .join(Submission, Submission.contributor_id == User.id)
            .join(Track, Track.id == Submission.track_id)
            .where(
                Submission.round_id.in_(round_ids),
                Submission.status == SubmissionStatus.ACCEPTED,
            )
            .order_by(User.display_name, User.email)
        )
    )
    contributors: dict[uuid.UUID, dict[str, str | None]] = {}
    artists: set[str] = set()
    for user_id, display_name, email, profile_image_url, artist in rows:
        contributors[user_id] = {
            "id": str(user_id),
            "displayName": display_name or email or "Unknown listener",
            "spotifyProfileImageUrl": profile_image_url,
        }
        artists.add(artist.casefold())
    return {
        "roundCount": len(rounds),
        "songCount": len(rows),
        "artistCount": len(artists),
        "contributors": sorted(
            contributors.values(), key=lambda contributor: str(contributor["displayName"]).casefold()
        ),
    }
