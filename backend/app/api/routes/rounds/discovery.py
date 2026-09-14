"""Finding something to submit: search, suggestions, and shared evidence."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

import httpx
from fastapi import Depends, HTTPException, Query, status
from sqlalchemy import func, select

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
    ContributorSubmissionCountResponse,
    EvidenceResponse,
    SubmissionResponse,
    TrackResponse,
)
from app.core.config import get_settings
from app.db.models import (
    ExternalAccount,
    ExternalProvider,
    ListeningEvidence,
    PublicationItem,
    Round,
    RoundMember,
    Submission,
    SubmissionStatus,
    Track,
    User,
)
from app.services import attribution, lastfm, spotify
from app.services.authorization import is_round_member, is_series_admin
from app.services.lifecycle import reconcile_round_status


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

    Nobody else's picks are revealed here until the round actually publishes -
    before that, only the viewer's own entries come back, whether the round is
    still open or sitting closed and waiting on Spotify. Use
    `/submission-counts` for a spoiler-free view of how much the group has
    shared so far.

    Once published, tracks appear for everyone so the attribution guessing
    game has something to play with, but *who* submitted each one stays
    hidden - contributor and note come back null - until this viewer's
    personal reveal condition is met (see `app.services.attribution`).
    """
    round_, membership = _viewer_round(db, round_id, user)
    if reconcile_round_status(round_):
        db.commit()
    publication = attribution.get_publication(db, round_id)
    has_published = publication is not None and publication.published_at is not None
    if not has_published:
        visible_statuses = Submission.contributor_id == user.id
    else:
        visible_statuses = Submission.status == SubmissionStatus.ACCEPTED
        if membership is not None:
            visible_statuses = visible_statuses | (Submission.contributor_id == user.id)
    revealed = has_published and attribution.is_revealed_for(db, round_, publication, user.id)
    spotify_profile_image = spotify_profile_image_subquery(Submission.contributor_id)
    query = (
        select(Submission, Track, User, spotify_profile_image)
        .join(Track, Track.id == Submission.track_id)
        .join(User, User.id == Submission.contributor_id)
        .where(
            Submission.round_id == round_id,
            visible_statuses,
        )
    )
    if has_published:
        # The published playlist's own (shuffled) order, so the guessing game
        # can't be won by noticing which tracks were submitted back to back.
        query = query.join(
            PublicationItem, PublicationItem.submission_id == Submission.id
        ).order_by(PublicationItem.position.asc())
    else:
        query = query.order_by(Submission.created_at.asc())
    rows = db.execute(query)
    return [
        {
            "id": str(submission.id),
            "status": submission.status.value,
            "note": submission.note if (revealed or submission.contributor_id == user.id) else None,
            "createdAt": submission.created_at.isoformat(),
            "updatedAt": submission.updated_at.isoformat(),
            "withdrawnAt": submission.withdrawn_at.isoformat() if submission.withdrawn_at else None,
            "isMine": submission.contributor_id == user.id,
            "contributor": (
                {
                    "id": str(contributor.id),
                    "displayName": contributor_display_name(
                        contributor.display_name, contributor.email
                    ),
                    "spotifyProfileImageUrl": profile_image_url,
                }
                if revealed or submission.contributor_id == user.id
                else None
            ),
            "track": _track_payload(track),
        }
        for submission, track, contributor, profile_image_url in rows
    ]


@router.get(
    "/{round_id}/submission-counts", response_model=list[ContributorSubmissionCountResponse]
)
def list_round_submission_counts(
    round_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> list[dict[str, object]]:
    """How many tracks each active round member has shared, never which ones.

    Lets the group see who's still quiet while a round is open without
    spoiling anyone's picks before `/submissions` reveals them at publication.
    Once published, exact per-person counts would let a guesser in the
    attribution game deduce assignments by elimination, so this stays empty
    for a viewer until their own reveal condition is met too.
    """
    round_, _membership = _viewer_round(db, round_id, user)
    publication = attribution.get_publication(db, round_id)
    has_published = publication is not None and publication.published_at is not None
    if has_published and not attribution.is_revealed_for(db, round_, publication, user.id):
        return []
    spotify_profile_image = spotify_profile_image_subquery(RoundMember.user_id)
    counts = (
        select(Submission.contributor_id, func.count().label("count"))
        .where(Submission.round_id == round_id, Submission.status == SubmissionStatus.ACCEPTED)
        .group_by(Submission.contributor_id)
        .subquery()
    )
    rows = db.execute(
        select(User, spotify_profile_image, func.coalesce(counts.c.count, 0))
        .select_from(RoundMember)
        .join(User, User.id == RoundMember.user_id)
        .outerjoin(counts, counts.c.contributor_id == RoundMember.user_id)
        .where(RoundMember.round_id == round_id, RoundMember.removed_at.is_(None))
        .order_by(User.display_name, User.email, User.id)
    )
    return [
        {
            "contributor": {
                "id": str(member.id),
                "displayName": contributor_display_name(member.display_name, member.email),
                "spotifyProfileImageUrl": profile_image_url,
            },
            "count": int(count),
        }
        for member, profile_image_url, count in rows
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
