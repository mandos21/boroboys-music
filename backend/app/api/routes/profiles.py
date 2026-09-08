"""Contributor listening profiles scoped to the rounds a viewer may already access."""

from __future__ import annotations

import base64
import binascii
import uuid
from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Select, and_, exists, func, or_, select, true
from sqlalchemy.engine import Row
from sqlalchemy.sql.elements import ColumnElement

from app.api.deps import DbSession, get_current_user
from app.api.payloads import contributor_display_name, spotify_profile_image_subquery
from app.api.routes.rounds._common import _track_payload
from app.api.schemas import ProfileResponse
from app.db.models import (
    PlatformRole,
    Round,
    RoundMember,
    Series,
    SeriesAdmin,
    Submission,
    SubmissionStatus,
    Track,
    TrackArtist,
    TrackGenre,
    User,
)
from app.services.genre_taxonomy import group_for

router = APIRouter(prefix="/profiles", tags=["profiles"])

_DEFAULT_HISTORY_LIMIT = 30
_MAX_HISTORY_LIMIT = 60
# Enough tags to show the long tail, few enough that the cloud stays the same
# height as the artists panel beside it.
_GENRE_SPREAD_LIMIT = 12
# Five is what fits the panel beside the artists list without scrolling.
_AFFINITY_LIMIT = 5
_SHARED_GENRE_LIMIT = 2


@router.get("/me", response_model=ProfileResponse)
def get_my_profile(
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=_MAX_HISTORY_LIMIT)] = _DEFAULT_HISTORY_LIMIT,
) -> dict[str, object]:
    return _profile_payload(db, user, user, cursor=cursor, limit=limit)


@router.get("/{user_id}", response_model=ProfileResponse)
def get_profile(
    user_id: uuid.UUID,
    db: DbSession,
    viewer: Annotated[User, Depends(get_current_user)],
    cursor: str | None = None,
    limit: Annotated[int, Query(ge=1, le=_MAX_HISTORY_LIMIT)] = _DEFAULT_HISTORY_LIMIT,
) -> dict[str, object]:
    profile_user = db.get(User, user_id)
    if profile_user is None or not profile_user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="profile not found")
    return _profile_payload(db, profile_user, viewer, cursor=cursor, limit=limit)


def _profile_payload(
    db: DbSession,
    profile_user: User,
    viewer: User,
    *,
    cursor: str | None,
    limit: int,
) -> dict[str, object]:
    """Build a profile without turning it into a side channel for private rounds.

    Aggregate queries intentionally run in PostgreSQL. History is cursor-paginated
    so a prolific contributor does not turn an ordinary profile view into an
    unbounded object graph in application memory.
    """
    visible = _visible_submissions(profile_user, viewer).cte("visible_submissions")
    summary = db.execute(
        select(
            func.count(visible.c.submission_id),
            func.count(func.distinct(visible.c.track_id)),
            func.count(
                func.distinct(
                    func.coalesce(visible.c.spotify_album_id, func.lower(visible.c.album))
                )
            ),
        )
    ).one()
    submission_count = int(summary[0])
    if (
        submission_count == 0
        and profile_user.id != viewer.id
        and viewer.platform_role is not PlatformRole.ADMIN
    ):
        # Do not disclose whether an otherwise unknown account exists.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="profile not found")

    artist_counts = db.execute(
        select(
            func.count(func.distinct(TrackArtist.spotify_artist_id)),
            func.count(TrackArtist.spotify_artist_id),
        ).join(visible, TrackArtist.track_id == visible.c.track_id)
    ).one()
    unique_artist_count, artist_credit_count = (int(value) for value in artist_counts)
    top_artists = _stat_items(
        db.execute(
            select(TrackArtist.name, func.count(visible.c.submission_id).label("count"))
            .join(visible, TrackArtist.track_id == visible.c.track_id)
            .group_by(TrackArtist.spotify_artist_id, TrackArtist.name)
            .order_by(func.count(visible.c.submission_id).desc(), func.lower(TrackArtist.name))
            .limit(5)
        ).all()
    )
    genre_counts = db.execute(
        select(
            func.count(func.distinct(TrackGenre.genre_key)),
            func.count(func.distinct(TrackGenre.track_id)),
        ).join(visible, TrackGenre.track_id == visible.c.track_id)
    ).one()
    genre_count, genre_tagged_track_count = (int(value) for value in genre_counts)
    genre_spread = [
        {**item, "group": group_for(str(item["name"]))}
        for item in _stat_items(
            db.execute(
                select(TrackGenre.name, func.count(visible.c.submission_id).label("count"))
                .join(visible, TrackGenre.track_id == visible.c.track_id)
                .group_by(TrackGenre.genre_key, TrackGenre.name)
                .order_by(func.count(visible.c.submission_id).desc(), func.lower(TrackGenre.name))
                .limit(_GENRE_SPREAD_LIMIT)
            ).all()
        )
    ]
    affinity = _taste_affinity(db, profile_user, viewer)

    history_statement = (
        select(Submission, Track, Round, Series)
        .join(Track, Track.id == Submission.track_id)
        .join(Round, Round.id == Submission.round_id)
        .join(Series, Series.id == Round.series_id)
        .where(
            Submission.contributor_id == profile_user.id,
            Submission.status == SubmissionStatus.ACCEPTED,
            _visible_round_predicate(profile_user, viewer),
        )
    )
    if cursor is not None:
        submitted_at, submission_id = _decode_cursor(cursor)
        history_statement = history_statement.where(
            or_(
                Submission.submitted_at < submitted_at,
                and_(Submission.submitted_at == submitted_at, Submission.id < submission_id),
            )
        )
    rows = list(
        db.execute(
            history_statement.order_by(Submission.submitted_at.desc(), Submission.id.desc()).limit(
                limit + 1
            )
        )
    )
    page = rows[:limit]
    next_cursor = _encode_cursor(page[-1][0]) if len(rows) > limit and page else None
    profile_image_url = db.scalar(
        select(spotify_profile_image_subquery(User.id)).where(User.id == profile_user.id)
    )

    return {
        "id": str(profile_user.id),
        "displayName": contributor_display_name(profile_user.display_name, profile_user.email),
        "spotifyProfileImageUrl": profile_image_url,
        "isMe": profile_user.id == viewer.id,
        "stats": {
            "submissionCount": submission_count,
            "uniqueTrackCount": int(summary[1]),
            "uniqueArtistCount": unique_artist_count,
            "uniqueAlbumCount": int(summary[2]),
            "uniqueGenreCount": genre_count,
            "genreTaggedTrackCount": genre_tagged_track_count,
            "diversityScore": round((unique_artist_count / artist_credit_count) * 100)
            if artist_credit_count
            else 0,
            "topArtists": top_artists,
            "genreSpread": genre_spread,
            "affinity": affinity,
        },
        "historyCount": submission_count,
        "nextCursor": next_cursor,
        "submissions": [
            {
                "id": str(submission.id),
                "submittedAt": submission.submitted_at.isoformat(),
                "note": submission.note,
                "track": _track_payload(track),
                "seriesId": str(series.id),
                "seriesName": series.name,
                "roundId": str(round_.id),
                "roundTitle": round_.title,
            }
            for submission, track, round_, series in page
        ],
    }


def _visible_submissions(
    profile_user: User, viewer: User
) -> Select[tuple[uuid.UUID, uuid.UUID, datetime, str | None, str | None]]:
    return (
        select(
            Submission.id.label("submission_id"),
            Submission.track_id,
            Submission.submitted_at,
            Track.spotify_album_id,
            Track.album,
        )
        .join(Track, Track.id == Submission.track_id)
        .join(Round, Round.id == Submission.round_id)
        .where(
            Submission.contributor_id == profile_user.id,
            Submission.status == SubmissionStatus.ACCEPTED,
            _visible_round_predicate(profile_user, viewer),
        )
    )


def _visible_round_predicate(profile_user: User, viewer: User) -> ColumnElement[bool]:
    if profile_user.id == viewer.id or viewer.platform_role is PlatformRole.ADMIN:
        return true()
    return or_(
        exists(
            select(RoundMember.round_id).where(
                RoundMember.round_id == Round.id,
                RoundMember.user_id == viewer.id,
                RoundMember.removed_at.is_(None),
            )
        ),
        exists(
            select(SeriesAdmin.series_id).where(
                SeriesAdmin.series_id == Round.series_id,
                SeriesAdmin.user_id == viewer.id,
            )
        ),
    )


def _stat_items(rows: Sequence[Row[tuple[str, int]]]) -> list[dict[str, object]]:
    return [{"name": name, "count": int(count)} for name, count in rows]


def _encode_cursor(submission: Submission) -> str:
    value = f"{submission.submitted_at.isoformat()}|{submission.id}"
    return base64.urlsafe_b64encode(value.encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        decoded = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        timestamp, submission_id = decoded.split("|", maxsplit=1)
        submitted_at = datetime.fromisoformat(timestamp)
        if submitted_at.tzinfo is None:
            raise ValueError
        return submitted_at, uuid.UUID(submission_id)
    except (UnicodeDecodeError, ValueError, binascii.Error):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid cursor"
        ) from None


def _taste_affinity(db: DbSession, profile_user: User, viewer: User) -> list[dict[str, object]]:
    """Rank the listeners whose genre mix most resembles this profile's.

    Similarity is histogram intersection over the genre groups: for each group,
    the smaller of the two shares, summed. That is symmetric, lands in 0-1
    without normalising twice, and is not distorted by one person simply
    submitting more than another.

    Only people who have actually shared a round with this profile are
    considered, and only rounds the viewer may see - so the panel cannot become
    a way to learn who is in a private round.
    """
    rows = db.execute(
        select(
            Submission.contributor_id,
            Submission.round_id,
            TrackGenre.name,
        )
        .join(Round, Round.id == Submission.round_id)
        .join(TrackGenre, TrackGenre.track_id == Submission.track_id)
        .where(
            Submission.status == SubmissionStatus.ACCEPTED,
            _visible_round_predicate(profile_user, viewer),
        )
    ).all()
    if not rows:
        return []

    genres_by_user: dict[uuid.UUID, Counter[str]] = defaultdict(Counter)
    rounds_by_user: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for contributor_id, round_id, genre in rows:
        genres_by_user[contributor_id][genre] += 1
        rounds_by_user[contributor_id].add(round_id)

    mine = genres_by_user.get(profile_user.id)
    if not mine:
        return []
    my_shares = _group_shares(mine)
    my_rounds = rounds_by_user[profile_user.id]

    scored: list[tuple[int, str, list[str], int]] = []
    for user_id, genres in genres_by_user.items():
        shared_rounds = my_rounds & rounds_by_user[user_id]
        if user_id == profile_user.id or not shared_rounds:
            continue
        theirs = _group_shares(genres)
        overlap = sum(min(my_shares.get(group, 0.0), theirs.get(group, 0.0)) for group in my_shares)
        shared = [name for name, _ in (mine & genres).most_common(_SHARED_GENRE_LIMIT)]
        scored.append((round(overlap * 100), str(user_id), shared, len(shared_rounds)))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return _with_identities(
        db,
        [
            {
                "id": user_id,
                "affinity": affinity,
                "sharedGenres": shared,
                "sharedRoundCount": rounds,
            }
            for affinity, user_id, shared, rounds in scored[:_AFFINITY_LIMIT]
        ],
    )


def _group_shares(genres: Counter[str]) -> dict[str, float]:
    """Turn a genre tally into the share of each group, so totals do not skew it."""
    groups: Counter[str] = Counter()
    for genre, count in genres.items():
        groups[group_for(genre)] += count
    total = sum(groups.values())
    return {group: count / total for group, count in groups.items()} if total else {}


def _with_identities(db: DbSession, items: list[dict[str, object]]) -> list[dict[str, object]]:
    if not items:
        return []
    ids = [uuid.UUID(str(item["id"])) for item in items]
    spotify_image = spotify_profile_image_subquery(User.id)
    identities = {
        str(user_id): (display_name, email, image)
        for user_id, display_name, email, image in db.execute(
            select(User.id, User.display_name, User.email, spotify_image).where(User.id.in_(ids))
        )
    }
    resolved = []
    for item in items:
        display_name, email, image = identities.get(str(item["id"]), (None, None, None))
        resolved.append(
            {
                **item,
                "displayName": contributor_display_name(display_name, email),
                "spotifyProfileImageUrl": image,
            }
        )
    return resolved
