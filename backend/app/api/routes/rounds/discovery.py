"""Finding something to submit: search, suggestions, and shared evidence."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

import httpx
from fastapi import Depends, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import DbSession, get_current_user
from app.api.payloads import (
    contributor_display_name,
    spotify_profile_image_subquery,
)
from app.api.routes.rounds._common import (
    _may_see_evidence,
    _member_round,
    _track_payload,
    _viewer_round,
    router,
)
from app.api.schemas import (
    EvidenceResponse,
    SubmissionResponse,
    TrackResponse,
)
from app.core.config import get_settings
from app.db.models import (
    ExternalAccount,
    ExternalProvider,
    ListeningEvidence,
    Round,
    RoundMember,
    Submission,
    SubmissionStatus,
    Track,
    User,
)
from app.services import lastfm, spotify
from app.services.authorization import is_round_member, is_series_admin


@router.get("/{round_id}/listening-suggestions")
def get_listening_suggestions(
    round_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> list[dict[str, str | None]]:
    _member_round(db, round_id, user.id)
    account = db.scalar(
        select(ExternalAccount).where(
            ExternalAccount.user_id == user.id,
            ExternalAccount.provider == ExternalProvider.LASTFM,
            ExternalAccount.is_active.is_(True),
        )
    )
    if account is None:
        return []
    try:
        return lastfm.monthly_top_tracks(get_settings(), account.provider_subject)
    except (httpx.HTTPError, lastfm.LastfmError, ValueError):
        return []


@router.get("/{round_id}/submissions", response_model=list[SubmissionResponse])
def list_round_submissions(
    round_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> list[dict[str, object]]:
    """Show accepted entries to round members and a user's withdrawn entries to them.

    The active membership check is intentional: a person removed from a private
    round must not retain a general read capability merely because their old
    submission remains attributable in publication history.
    """
    _, membership = _viewer_round(db, round_id, user)
    visible_statuses = Submission.status == SubmissionStatus.ACCEPTED
    if membership is not None:
        visible_statuses = visible_statuses | (Submission.contributor_id == user.id)
    spotify_profile_image = spotify_profile_image_subquery(Submission.contributor_id)
    rows = db.execute(
        select(Submission, Track, User, spotify_profile_image)
        .join(Track, Track.id == Submission.track_id)
        .join(User, User.id == Submission.contributor_id)
        .where(
            Submission.round_id == round_id,
            visible_statuses,
        )
        .order_by(Submission.created_at.asc())
    )
    return [
        {
            "id": str(submission.id),
            "status": submission.status.value,
            "note": submission.note,
            "createdAt": submission.created_at.isoformat(),
            "updatedAt": submission.updated_at.isoformat(),
            "withdrawnAt": submission.withdrawn_at.isoformat() if submission.withdrawn_at else None,
            "isMine": submission.contributor_id == user.id,
            "contributor": {
                "id": str(contributor.id),
                "displayName": contributor_display_name(
                    contributor.display_name, contributor.email
                ),
                "spotifyProfileImageUrl": profile_image_url,
            },
            "track": _track_payload(track),
        }
        for submission, track, contributor, profile_image_url in rows
    ]


@router.get("/{round_id}/track-search", response_model=list[TrackResponse])
def search_tracks(
    round_id: uuid.UUID,
    query: Annotated[str, Query(min_length=2, max_length=200)],
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> list[dict[str, object]]:
    _member_round(db, round_id, user.id)
    try:
        # Catalog search is public data, not personal to whoever is asking, so
        # it runs on the app's own Client Credentials grant rather than
        # requiring every contributor to hold their own Spotify authorization
        # (Spotify's Development Mode caps that at a handful of accounts).
        access_token = spotify.client_credentials_token(get_settings())
        matches = spotify.search_tracks(access_token, query)
    except (httpx.HTTPError, spotify.SpotifyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Spotify search failed"
        ) from None
    return [
        _search_result_payload(item)
        for item in matches
        if isinstance(item.get("id"), str) and isinstance(item.get("name"), str)
    ]


def _search_result_payload(item: dict[str, Any]) -> dict[str, object]:
    """Shape one Spotify search hit without trusting any nested field's type.

    Search results are only a picker; the canonical lookup at submission time
    re-reads the track. That is no reason for an odd payload to 500 the
    search itself, so every nested access is type-checked.
    """
    artists = item.get("artists")
    artist_names = (
        [
            artist["name"]
            for artist in artists
            if isinstance(artist, dict) and isinstance(artist.get("name"), str)
        ]
        if isinstance(artists, list)
        else []
    )
    raw_album = item.get("album")
    album: dict[str, Any] = raw_album if isinstance(raw_album, dict) else {}
    raw_images = album.get("images")
    images: list[Any] = raw_images if isinstance(raw_images, list) else []
    artwork_url = next(
        (
            image["url"]
            for image in images
            if isinstance(image, dict) and isinstance(image.get("url"), str)
        ),
        None,
    )
    return {
        "spotifyTrackId": item["id"],
        "name": item["name"],
        "artist": ", ".join(artist_names),
        "album": album.get("name") if isinstance(album.get("name"), str) else None,
        "spotifyUri": item.get("uri") if isinstance(item.get("uri"), str) else None,
        "artworkUrl": artwork_url,
        "providerMetadata": {
            "explicit": item.get("explicit") is True,
            "isPlayable": item.get("is_playable") is not False,
        },
    }


@router.get("/{round_id}/tracks/{track_id}/evidence", response_model=EvidenceResponse)
def get_evidence(
    round_id: uuid.UUID,
    track_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, object]:
    round_ = db.get(Round, round_id)
    if round_ is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="round not found")
    is_member = is_round_member(db, round_id, user.id)
    viewer_is_series_admin = is_series_admin(db, round_.series_id, user)
    if not is_member and not viewer_is_series_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="round access required")
    rows = list(
        db.execute(
            select(ExternalAccount, ListeningEvidence)
            .join(ListeningEvidence, ListeningEvidence.external_account_id == ExternalAccount.id)
            .join(RoundMember, RoundMember.user_id == ExternalAccount.user_id)
            .where(
                RoundMember.round_id == round_.id,
                RoundMember.removed_at.is_(None),
                ExternalAccount.provider == ExternalProvider.LASTFM,
                ListeningEvidence.track_id == track_id,
            )
        )
    )
    evidence = []
    for account, item in rows:
        if not _may_see_evidence(
            account, user, is_member=is_member, is_series_admin=viewer_is_series_admin
        ):
            continue
        evidence.append(
            {
                "accountId": str(account.id),
                "displayName": account.display_name,
                "isMine": account.user_id == user.id,
                "playcount": item.playcount,
                "artistPlaycount": item.artist_playcount,
                "albumPlaycount": item.album_playcount,
                "fetchedAt": item.fetched_at.isoformat(),
                "refreshAfter": item.refresh_after.isoformat() if item.refresh_after else None,
                "status": item.response_status,
            }
        )
    return {"roundId": str(round_.id), "trackId": str(track_id), "evidence": evidence}
