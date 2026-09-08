"""Contributor-visible series history without leaking other private round groups."""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, or_, select

from app.api.deps import DbSession, get_current_user, require_csrf
from app.api.payloads import (
    contributor_display_name,
    round_artwork_urls_by_round,
    round_timeline,
    spotify_profile_image_subquery,
    stable_pick,
)
from app.api.schemas import SeriesHistoryResponse, SeriesListResponse
from app.core.security import hash_secret
from app.db.models import (
    ContributorGroup,
    ContributorGroupMember,
    PlatformRole,
    Round,
    RoundMember,
    RoundStatus,
    Series,
    SeriesAdmin,
    SeriesInvite,
    Submission,
    SubmissionStatus,
    Track,
    TrackGenre,
    User,
)
from app.services.authorization import is_series_admin
from app.services.genre_taxonomy import GROUPS, group_for
from app.services.lifecycle import reconcile_round_status
from app.services.membership import ensure_default_series_membership

router = APIRouter(prefix="/series", tags=["series"])

# Matches the profile cloud, which sits at the same width.
_SERIES_GENRE_LIMIT = 12


@router.post("/invites/{token}/accept", dependencies=[Depends(require_csrf)])
def accept_series_invite(
    token: str,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, object]:
    invite = db.scalar(
        select(SeriesInvite).where(SeriesInvite.token_hash == hash_secret(token)).with_for_update()
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


@router.get("", response_model=list[SeriesListResponse])
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
    payloads = _series_payloads(db, series_items, user)
    return sorted(payloads, key=_series_sort_key)


@router.get("/{series_id}", response_model=SeriesHistoryResponse)
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
    is_admin = is_series_admin(db, series_id, user)
    rounds = _visible_rounds(db, series_id, user, is_admin)
    if not is_admin and not rounds and not _has_series_membership(db, series_id, user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="series access required")
    stats = _series_stats(db, rounds)
    artwork_by_round = round_artwork_urls_by_round(db, [round_.id for round_ in rounds])
    fallback_artwork_url = (
        _fallback_artwork_url(rounds, artwork_by_round)
        if not series.cover_image_url and not series.accent_color
        else None
    )
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
                **round_timeline(round_),
                "artworkUrls": artwork_by_round.get(round_.id, []),
            }
            for round_ in rounds
        ],
    }


def _series_payloads(
    db: DbSession, series_items: list[Series], user: User
) -> list[dict[str, object]]:
    """Build the dashboard in a fixed number of queries, not per series.

    The landing page is deliberately a broad view: a person with ten series
    should not pay ten copies of the round, count, and artwork lookups.
    """
    series_ids = [series.id for series in series_items]
    if not series_ids:
        return []
    admin_series_ids = set(
        db.scalars(
            select(SeriesAdmin.series_id).where(
                SeriesAdmin.user_id == user.id,
                SeriesAdmin.series_id.in_(series_ids),
            )
        )
    )
    is_platform_admin = user.platform_role is PlatformRole.ADMIN
    membership = (RoundMember.user_id == user.id) & RoundMember.removed_at.is_(None)
    round_query = select(Round).where(Round.series_id.in_(series_ids))
    if not is_platform_admin:
        round_query = (
            round_query.outerjoin(RoundMember, RoundMember.round_id == Round.id)
            .where(or_(membership, Round.series_id.in_(admin_series_ids)))
            .distinct()
        )
    visible_rounds = list(db.scalars(round_query))
    if any(reconcile_round_status(round_) for round_ in visible_rounds):
        db.commit()

    round_ids = [round_.id for round_ in visible_rounds]
    submitted_counts: dict[uuid.UUID, int] = {}
    contributor_counts: dict[uuid.UUID, int] = {}
    artwork_by_round: dict[uuid.UUID, list[str]] = {}
    if round_ids:
        submitted_counts = {
            round_id: int(count)
            for round_id, count in db.execute(
                select(Submission.round_id, func.count(func.distinct(Submission.contributor_id)))
                .where(
                    Submission.round_id.in_(round_ids),
                    Submission.status == SubmissionStatus.ACCEPTED,
                )
                .group_by(Submission.round_id)
            )
        }
        contributor_counts = {
            round_id: int(count)
            for round_id, count in db.execute(
                select(RoundMember.round_id, func.count())
                .where(
                    RoundMember.round_id.in_(round_ids),
                    RoundMember.removed_at.is_(None),
                )
                .group_by(RoundMember.round_id)
            )
        }
        for round_id, artwork_url in db.execute(
            select(Submission.round_id, Track.artwork_url)
            .join(Track, Track.id == Submission.track_id)
            .where(
                Submission.round_id.in_(round_ids),
                Submission.status == SubmissionStatus.ACCEPTED,
                Track.artwork_url.is_not(None),
            )
            .order_by(Submission.created_at, Submission.id)
        ):
            if isinstance(artwork_url, str):
                artwork_by_round.setdefault(round_id, []).append(artwork_url)

    rounds_by_series: dict[uuid.UUID, list[Round]] = {series_id: [] for series_id in series_ids}
    for round_ in visible_rounds:
        rounds_by_series[round_.series_id].append(round_)
    payloads: list[dict[str, object]] = []
    for series in series_items:
        rounds = sorted(rounds_by_series[series.id], key=_round_sort_key)
        featured = next((round_ for round_ in rounds if round_.status is RoundStatus.OPEN), None)
        featured = featured or next(
            (round_ for round_ in rounds if round_.status is not RoundStatus.PUBLISHED), None
        )
        featured = featured or (rounds[0] if rounds else None)
        artwork_urls = artwork_by_round.get(featured.id, []) if featured else []
        fallback_artwork_url = (
            artwork_urls[featured.id.int % len(artwork_urls)]
            if featured and artwork_urls and not series.cover_image_url and not series.accent_color
            else None
        )
        payloads.append(
            {
                "id": str(series.id),
                "name": series.name,
                "description": series.description,
                "timezone": series.timezone,
                "coverImageUrl": series.cover_image_url,
                "accentColor": series.accent_color,
                "fallbackArtworkUrl": fallback_artwork_url,
                "isAdmin": is_platform_admin or series.id in admin_series_ids,
                "featuredRound": _round_payload_from_counts(
                    featured, submitted_counts, contributor_counts
                )
                if featured
                else None,
            }
        )
    return payloads


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
    return sorted(rounds, key=_round_sort_key)


def _round_sort_key(round_: Round) -> tuple[int, float]:
    return (
        0
        if round_.status is RoundStatus.OPEN
        else 1
        if round_.status is not RoundStatus.PUBLISHED
        else 2,
        -round_.opens_at.timestamp(),
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


def _round_payload_from_counts(
    round_: Round,
    submitted_counts: dict[uuid.UUID, int],
    contributor_counts: dict[uuid.UUID, int],
) -> dict[str, object]:
    return {
        **round_timeline(round_),
        "submittedCount": submitted_counts.get(round_.id, 0),
        "contributorCount": contributor_counts.get(round_.id, 0),
    }


def _fallback_artwork_url(
    rounds: Sequence[Round | None], artwork_by_round: dict[uuid.UUID, list[str]]
) -> str | None:
    for round_ in rounds:
        if round_ is None:
            continue
        artwork_urls = artwork_by_round.get(round_.id, [])
        if artwork_urls:
            # A rotating offset keeps a no-theme series visually musical without
            # persisting a separate identity just for its first release.
            return stable_pick(artwork_urls, round_.id)
    return None


def _series_stats(db: DbSession, rounds: list[Round]) -> dict[str, object]:
    if not rounds:
        return {
            "roundCount": 0,
            "songCount": 0,
            "artistCount": 0,
            "genreTaggedTrackCount": 0,
            "uniqueTrackCount": 0,
            "genreSpread": [],
            "contributors": [],
        }
    round_ids = [round_.id for round_ in rounds]
    spotify_profile_image = spotify_profile_image_subquery(User.id)
    rows = list(
        db.execute(
            select(
                User.id,
                User.display_name,
                User.email,
                spotify_profile_image,
                Track.artist,
                Submission.track_id,
            )
            .join(Submission, Submission.contributor_id == User.id)
            .join(Track, Track.id == Submission.track_id)
            .where(
                Submission.round_id.in_(round_ids),
                Submission.status == SubmissionStatus.ACCEPTED,
            )
            .order_by(User.display_name, User.email)
        )
    )
    contributors: dict[uuid.UUID, dict[str, object]] = {}
    tracks_by_contributor: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    track_ids: set[uuid.UUID] = set()
    artists: set[str] = set()
    for user_id, display_name, email, profile_image_url, artist, track_id in rows:
        tracks_by_contributor[user_id].add(track_id)
        track_ids.add(track_id)
        contributors[user_id] = {
            "id": str(user_id),
            "displayName": contributor_display_name(display_name, email),
            "spotifyProfileImageUrl": profile_image_url,
        }
        artists.add(artist.casefold())

    spread: Counter[str] = Counter()
    groups_by_contributor: dict[uuid.UUID, Counter[str]] = defaultdict(Counter)
    tagged_tracks: set[uuid.UUID] = set()
    for contributor_id, genre, track_id in db.execute(
        select(Submission.contributor_id, TrackGenre.name, Submission.track_id)
        .join(TrackGenre, TrackGenre.track_id == Submission.track_id)
        .where(
            Submission.round_id.in_(round_ids),
            Submission.status == SubmissionStatus.ACCEPTED,
        )
    ):
        spread[genre] += 1
        groups_by_contributor[contributor_id][group_for(genre)] += 1
        tagged_tracks.add(track_id)

    return {
        "roundCount": len(rounds),
        "songCount": len(rows),
        "artistCount": len(artists),
        "genreTaggedTrackCount": len(tagged_tracks),
        "uniqueTrackCount": len(track_ids),
        "genreSpread": [
            {"name": name, "count": count, "group": group_for(name)}
            for name, count in spread.most_common(_SERIES_GENRE_LIMIT)
        ],
        "contributors": sorted(
            (
                {
                    **contributor,
                    "trackCount": len(tracks_by_contributor[user_id]),
                    # Stacked in the shared group order so one person's mix can
                    # be read against another's rather than each finding its own.
                    "groups": [
                        {"group": group, "count": groups_by_contributor[user_id][group]}
                        for group in GROUPS
                        if groups_by_contributor[user_id][group]
                    ],
                }
                for user_id, contributor in contributors.items()
            ),
            key=lambda contributor: str(contributor["displayName"]).casefold(),
        ),
    }
