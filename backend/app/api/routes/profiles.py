"""Contributor listening profiles scoped to the rounds a viewer may already access."""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import exists, or_, select, true
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
    User,
)

router = APIRouter(prefix="/profiles", tags=["profiles"])

_HISTORY_LIMIT = 60


@router.get("/me", response_model=ProfileResponse)
def get_my_profile(
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, object]:
    return _profile_payload(db, user, user)


@router.get("/{user_id}", response_model=ProfileResponse)
def get_profile(
    user_id: uuid.UUID,
    db: DbSession,
    viewer: Annotated[User, Depends(get_current_user)],
) -> dict[str, object]:
    profile_user = db.get(User, user_id)
    if profile_user is None or not profile_user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="profile not found")
    return _profile_payload(db, profile_user, viewer)


def _profile_payload(db: DbSession, profile_user: User, viewer: User) -> dict[str, object]:
    """Build a profile without turning it into a side channel for private rounds.

    A person sees their own accepted history. Everyone else only sees submissions from a
    round they can still enter, unless they are a platform administrator. The same predicate
    is deliberately applied to aggregate stats and the timeline.
    """
    visible_round = _visible_round_predicate(profile_user, viewer)
    statement = (
        select(Submission, Track, Round, Series)
        .join(Track, Track.id == Submission.track_id)
        .join(Round, Round.id == Submission.round_id)
        .join(Series, Series.id == Round.series_id)
        .where(
            Submission.contributor_id == profile_user.id,
            Submission.status == SubmissionStatus.ACCEPTED,
            visible_round,
        )
        .order_by(Submission.submitted_at.desc(), Submission.id.desc())
    )
    rows = list(db.execute(statement))
    if not rows and profile_user.id != viewer.id and viewer.platform_role is not PlatformRole.ADMIN:
        # Do not disclose whether an otherwise unknown account exists.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="profile not found")

    profile_image_url = db.scalar(
        select(spotify_profile_image_subquery(User.id)).where(User.id == profile_user.id)
    )
    artists = Counter[str]()
    albums: set[str] = set()
    tracks: set[str] = set()
    genres = Counter[str]()
    activity = Counter[str]()
    for submission, track, _, _ in rows:
        artists[track.artist] += 1
        tracks.add(track.spotify_track_id)
        if track.album:
            albums.add(track.album.casefold())
        genres.update(_track_genres(track.provider_metadata))
        activity[submission.submitted_at.astimezone(UTC).strftime("%Y-%m")] += 1

    return {
        "id": str(profile_user.id),
        "displayName": contributor_display_name(profile_user.display_name, profile_user.email),
        "spotifyProfileImageUrl": profile_image_url,
        "isMe": profile_user.id == viewer.id,
        "stats": {
            "submissionCount": len(rows),
            "uniqueTrackCount": len(tracks),
            "uniqueArtistCount": len(artists),
            "uniqueAlbumCount": len(albums),
            "uniqueGenreCount": len(genres),
            "diversityScore": round((len(artists) / len(rows)) * 100) if rows else 0,
            "topArtists": _ranked_items(artists, limit=5),
            "genreSpread": _ranked_items(genres, limit=8),
            "activity": _activity_months(activity),
        },
        "historyCount": len(rows),
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
            for submission, track, round_, series in rows[:_HISTORY_LIMIT]
        ],
    }


def _visible_round_predicate(profile_user: User, viewer: User) -> ColumnElement[bool]:
    if profile_user.id == viewer.id or viewer.platform_role is PlatformRole.ADMIN:
        return true()
    return or_(
        exists(
            select(RoundMember.id).where(
                RoundMember.round_id == Round.id,
                RoundMember.user_id == viewer.id,
                RoundMember.removed_at.is_(None),
            )
        ),
        exists(
            select(SeriesAdmin.id).where(
                SeriesAdmin.series_id == Round.series_id,
                SeriesAdmin.user_id == viewer.id,
            )
        ),
    )


def _track_genres(metadata: dict[str, Any]) -> list[str]:
    value = metadata.get("genres")
    if not isinstance(value, list):
        return []
    return [genre.strip() for genre in value if isinstance(genre, str) and genre.strip()]


def _ranked_items(counter: Counter[str], *, limit: int) -> list[dict[str, object]]:
    return [
        {"name": name, "count": count}
        for name, count in sorted(counter.items(), key=lambda item: (-item[1], item[0].casefold()))[
            :limit
        ]
    ]


def _activity_months(activity: Counter[str]) -> list[dict[str, object]]:
    if not activity:
        return []
    return [
        {
            "month": key,
            "label": _activity_label(key),
            "count": activity[key],
        }
        for key in sorted(activity)[-12:]
    ]


def _activity_label(key: str) -> str:
    year, month = (int(part) for part in key.split("-"))
    return datetime(year, month, 1, tzinfo=UTC).strftime("%b %Y")
