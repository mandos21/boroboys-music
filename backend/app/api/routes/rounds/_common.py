"""The router the round modules share, plus the helpers more than one uses."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.api.deps import DbSession
from app.db.models import (
    EvidenceVisibility,
    ExternalAccount,
    ExternalProvider,
    Round,
    RoundMember,
    RoundStatus,
    Submission,
    SubmissionStatus,
    Track,
    User,
)
from app.services import spotify
from app.services.authorization import is_series_admin
from app.services.lifecycle import reconcile_round_status
from app.services.publications import get_spotify_access_token
from app.services.track_metadata import sync_track_artists

router = APIRouter(prefix="/rounds", tags=["rounds"])


class TrackArtistInput(BaseModel):
    spotify_artist_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=500)
    position: int = Field(ge=0)


class TrackInput(BaseModel):
    spotify_track_id: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=500)
    artist: str = Field(min_length=1, max_length=500)
    album: str | None = Field(default=None, max_length=500)
    spotify_album_id: str | None = Field(default=None, max_length=64)
    spotify_uri: str | None = Field(default=None, max_length=128)
    artwork_url: str | None = Field(default=None, max_length=1000)
    provider_metadata: dict[str, Any] = Field(default_factory=dict)
    artists: list[TrackArtistInput] = Field(default_factory=list)


def _may_see_evidence(
    account: ExternalAccount, user: User, *, is_member: bool, is_series_admin: bool
) -> bool:
    """Apply the visibility ladder a listener chose for their own history.

    The settings are ordered from most to least open: round members, then series
    administrators, then nobody. A series administrator is more privileged than a
    round member, so anything shared with round members is also visible to them.
    """
    if account.user_id == user.id:
        return True
    if account.evidence_visibility is EvidenceVisibility.PRIVATE:
        return False
    if account.evidence_visibility is EvidenceVisibility.SERIES_ADMINS:
        return is_series_admin
    return is_member or is_series_admin


def _member_round(
    db: DbSession, round_id: uuid.UUID, user_id: uuid.UUID, lock_round: bool = False
) -> tuple[Round, RoundMember]:
    query = select(Round).where(Round.id == round_id)
    if lock_round:
        query = query.with_for_update()
    round_ = db.scalar(query)
    if round_ is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="round not found")
    membership = db.scalar(
        select(RoundMember).where(
            RoundMember.round_id == round_id,
            RoundMember.user_id == user_id,
            RoundMember.removed_at.is_(None),
        )
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="round membership required"
        )
    return round_, membership


def _viewer_round(
    db: DbSession, round_id: uuid.UUID, user: User
) -> tuple[Round, RoundMember | None]:
    """Authorize a contributor or the series' normal administrator.

    A series administrator has management access without becoming a contributor.
    That is not a separate round-administrator role, and it does not allow the
    administrator to submit or inspect a contributor's withdrawn entry.
    """
    round_ = db.get(Round, round_id)
    if round_ is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="round not found")
    membership = db.scalar(
        select(RoundMember).where(
            RoundMember.round_id == round_id,
            RoundMember.user_id == user.id,
            RoundMember.removed_at.is_(None),
        )
    )
    if membership is not None:
        return round_, membership
    if not is_series_admin(db, round_.series_id, user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="round access required")
    return round_, None


def _require_open_round(round_: Round) -> None:
    # Reconcile first so a round whose opening time has passed is not refused
    # merely because no worker has moved it out of `scheduled` yet.
    reconcile_round_status(round_)
    now = datetime.now(UTC)
    if round_.status is not RoundStatus.OPEN or not (round_.opens_at <= now < round_.closes_at):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="round is not accepting submissions"
        )


def _submission_limit(round_: Round, membership: RoundMember) -> int:
    return (
        membership.submission_limit_override
        if membership.submission_limit_override is not None
        else round_.submission_limit
    )


def _active_submission_count(db: DbSession, round_id: uuid.UUID, user_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(Submission)
            .where(
                Submission.round_id == round_id,
                Submission.contributor_id == user_id,
                Submission.status == SubmissionStatus.ACCEPTED,
            )
        )
        or 0
    )


def _canonical_track_input(db: DbSession, user: User, input_track: TrackInput) -> TrackInput:
    """Resolve a client-selected Spotify ID into trusted provider metadata.

    Search results are a UI convenience, never an authority.  Policies and
    publication snapshots must be based on Spotify's response, not fields a
    browser can alter before posting a submission.
    """
    account = db.scalar(
        select(ExternalAccount).where(
            ExternalAccount.user_id == user.id,
            ExternalAccount.provider == ExternalProvider.SPOTIFY,
            ExternalAccount.is_active.is_(True),
        )
    )
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Spotify account is not linked"
        )
    try:
        access_token = get_spotify_access_token(db, account.id)
        # Token refreshes are durable state and should survive a later provider
        # failure. This also keeps remote I/O outside an open write transaction.
        db.commit()
        matches = spotify.tracks_by_id(access_token, [input_track.spotify_track_id])
    except (httpx.HTTPError, spotify.SpotifyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail="Spotify track lookup failed"
        ) from None
    track = next(
        (
            item
            for item in matches
            if isinstance(item.get("id"), str) and item["id"] == input_track.spotify_track_id
        ),
        None,
    )
    if track is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Spotify could not find that track for your account",
        )
    name = track.get("name")
    uri = track.get("uri")
    artists = track.get("artists")
    artist_names = (
        [
            item["name"]
            for item in artists
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        ]
        if isinstance(artists, list)
        else []
    )
    artist_inputs = (
        [
            TrackArtistInput(spotify_artist_id=item["id"], name=item["name"], position=position)
            for position, item in enumerate(artists)
            if isinstance(item, dict)
            and isinstance(item.get("id"), str)
            and isinstance(item.get("name"), str)
        ]
        if isinstance(artists, list)
        else []
    )
    artist = ", ".join(artist_names)
    if not isinstance(name, str) or not isinstance(uri, str) or not artist:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Spotify returned incomplete track metadata",
        )
    album_data = track.get("album")
    album = album_data.get("name") if isinstance(album_data, dict) else None
    artwork_url = None
    if isinstance(album_data, dict) and isinstance(album_data.get("images"), list):
        for image in album_data["images"]:
            if isinstance(image, dict) and isinstance(image.get("url"), str):
                artwork_url = image["url"]
                break
    metadata: dict[str, Any] = {
        "explicit": track.get("explicit") is True,
        "isPlayable": track.get("is_playable") is not False,
    }
    return TrackInput(
        spotify_track_id=input_track.spotify_track_id,
        name=name,
        artist=artist,
        album=album if isinstance(album, str) else None,
        spotify_album_id=(
            album_data.get("id")
            if isinstance(album_data, dict) and isinstance(album_data.get("id"), str)
            else None
        ),
        spotify_uri=uri,
        artwork_url=artwork_url,
        provider_metadata=metadata,
        artists=artist_inputs,
    )


def _find_or_create_track(db: DbSession, input_track: TrackInput) -> Track:
    track = db.scalar(select(Track).where(Track.spotify_track_id == input_track.spotify_track_id))
    if track is not None:
        track.name = input_track.name
        track.artist = input_track.artist
        track.album = input_track.album
        track.spotify_album_id = input_track.spotify_album_id
        track.spotify_uri = input_track.spotify_uri
        track.artwork_url = input_track.artwork_url
        # Provider fields such as playability should refresh, while optional
        # enrichment remains additive: a transient lookup failure must never
        # make a previously known genre disappear.
        track.provider_metadata = {**track.provider_metadata, **input_track.provider_metadata}
        sync_track_artists(
            db,
            track,
            [
                (artist.spotify_artist_id, artist.name, artist.position)
                for artist in input_track.artists
            ],
        )
        return track
    # Tracks are shared across overlapping rounds.  PostgreSQL resolves the
    # first-insert race without turning a normal simultaneous evaluation into
    # an IntegrityError/500.
    result = db.execute(
        insert(Track)
        .values(**input_track.model_dump(exclude={"artists"}))
        .on_conflict_do_nothing(index_elements=[Track.spotify_track_id])
        .returning(Track.id)
    )
    track_id = result.scalar_one_or_none()
    if track_id is not None:
        track = db.get(Track, track_id)
    else:
        track = db.scalar(
            select(Track).where(Track.spotify_track_id == input_track.spotify_track_id)
        )
    if track is None:  # defensive: only possible with an unexpected transaction failure
        raise RuntimeError("track insert did not return a track")
    sync_track_artists(
        db,
        track,
        [
            (artist.spotify_artist_id, artist.name, artist.position)
            for artist in input_track.artists
        ],
    )
    return track


def _policy_payload(result: Any) -> dict[str, object]:
    return {
        "kind": result.kind,
        "version": result.version,
        "decision": result.decision.value,
        "message": result.message,
        "result": result.result,
    }


def _track_payload(track: Track) -> dict[str, object]:
    return {
        "spotifyTrackId": track.spotify_track_id,
        "name": track.name,
        "artist": track.artist,
        "album": track.album,
        "spotifyUri": track.spotify_uri,
        "artworkUrl": track.artwork_url,
    }
