"""Contributor listening profiles scoped to the rounds a viewer may already access."""

from __future__ import annotations

import base64
import binascii
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
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

router = APIRouter(prefix="/profiles", tags=["profiles"])

_DEFAULT_HISTORY_LIMIT = 30
_MAX_HISTORY_LIMIT = 60


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
    genre_spread = _stat_items(
        db.execute(
            select(TrackGenre.name, func.count(visible.c.submission_id).label("count"))
            .join(visible, TrackGenre.track_id == visible.c.track_id)
            .group_by(TrackGenre.genre_key, TrackGenre.name)
            .order_by(func.count(visible.c.submission_id).desc(), func.lower(TrackGenre.name))
            .limit(8)
        ).all()
    )
    activity = _calendar_activity(
        db.execute(
            select(
                func.date_trunc("month", visible.c.submitted_at).label("month"),
                func.count(visible.c.submission_id).label("count"),
            )
            .group_by("month")
            .order_by("month")
        ).all()
    )

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
            "activity": activity,
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


def _calendar_activity(rows: Sequence[Row[tuple[datetime, int]]]) -> list[dict[str, object]]:
    """Show a contiguous final year, including quiet months, not sparse months."""
    if not rows:
        return []
    counts = {month.strftime("%Y-%m"): int(count) for month, count in rows}
    latest = max(month for month, _ in rows).astimezone(UTC)
    months = [_month_before(latest, offset) for offset in range(11, -1, -1)]
    return [
        {
            "month": month.strftime("%Y-%m"),
            "label": month.strftime("%b %Y"),
            "count": counts.get(month.strftime("%Y-%m"), 0),
        }
        for month in months
    ]


def _month_before(month: datetime, offset: int) -> datetime:
    index = month.year * 12 + month.month - 1 - offset
    return datetime(index // 12, index % 12 + 1, 1, tzinfo=UTC)


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
