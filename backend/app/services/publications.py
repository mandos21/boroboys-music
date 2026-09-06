"""Durable publication snapshots and constrained state transitions."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import decrypt, encrypt
from app.db.models import (
    AuditEvent,
    ExternalAccount,
    ExternalCredential,
    ExternalProvider,
    Publication,
    PublicationItem,
    PublicationState,
    Round,
    RoundStatus,
    Series,
    Submission,
    SubmissionStatus,
    Track,
)
from app.services import spotify
from app.services.lifecycle import create_successor


class PublicationError(Exception):
    pass


def start_publication(
    db: Session,
    round_id: uuid.UUID,
    publisher_account_id: uuid.UUID,
    publisher_owner_id: uuid.UUID,
) -> Publication:
    # Lock the series before allocating its publication sequence.  Locking only
    # the round permits two different rounds in the same series to choose the
    # same next sequence concurrently.
    candidate = db.get(Round, round_id)
    if candidate is None:
        raise PublicationError("round must be closed before publication")
    series = db.scalar(select(Series).where(Series.id == candidate.series_id).with_for_update())
    if series is None:
        raise PublicationError("series not found")
    round_ = db.scalar(select(Round).where(Round.id == round_id).with_for_update())
    if round_ is None or round_.status is not RoundStatus.CLOSED:
        raise PublicationError("round must be closed before publication")
    if db.scalar(select(Publication).where(Publication.round_id == round_id)):
        raise PublicationError("round already has a publication")
    publisher = db.get(ExternalAccount, publisher_account_id)
    if (
        publisher is None
        or publisher.provider is not ExternalProvider.SPOTIFY
        or not publisher.is_active
        or publisher.user_id != publisher_owner_id
    ):
        raise PublicationError("a connected Spotify publisher is required")
    if db.scalar(
        select(ExternalCredential.id).where(ExternalCredential.external_account_id == publisher.id)
    ) is None:
        raise PublicationError("Spotify publisher needs reauthorization")
    sequence = (
        db.scalar(
            select(func.max(Round.published_sequence)).where(Round.series_id == round_.series_id)
        )
        or 0
    ) + 1
    publication = Publication(
        round_id=round_.id,
        publisher_account_id=publisher_account_id,
        idempotency_key=str(uuid.uuid4()),
        state=PublicationState.PUBLISHING,
    )
    db.add(publication)
    db.flush()
    submissions = list(
        db.scalars(
            select(Submission)
            .where(Submission.round_id == round_.id, Submission.status == SubmissionStatus.ACCEPTED)
            .order_by(Submission.submitted_at, Submission.id)
        )
    )
    db.add_all(
        PublicationItem(
            publication_id=publication.id,
            submission_id=item.id,
            track_id=item.track_id,
            contributor_id=item.contributor_id,
            position=index,
            note_snapshot=item.note,
        )
        for index, item in enumerate(submissions, start=1)
    )
    round_.status = RoundStatus.PUBLISHING
    round_.publisher_account_id = publisher.id
    round_.published_sequence = sequence
    return publication


def mark_published(db: Session, publication_id: uuid.UUID, playlist_id: str) -> Publication:
    publication = db.scalar(
        select(Publication).where(Publication.id == publication_id).with_for_update()
    )
    if publication is None:
        raise PublicationError("publication not found")
    round_ = db.get(Round, publication.round_id)
    if round_ is None:
        raise PublicationError("round not found")
    publication.spotify_playlist_id = playlist_id
    publication.state = PublicationState.PUBLISHED
    round_.status = RoundStatus.PUBLISHED
    create_successor(db, round_)
    return publication


def start_unpublish(db: Session, round_id: uuid.UUID) -> Publication:
    candidate = db.get(Round, round_id)
    if candidate is None:
        raise PublicationError("round is not published")
    series = db.scalar(select(Series).where(Series.id == candidate.series_id).with_for_update())
    if series is None:
        raise PublicationError("series not found")
    round_ = db.scalar(select(Round).where(Round.id == round_id).with_for_update())
    if round_ is None or round_.status is not RoundStatus.PUBLISHED:
        raise PublicationError("round is not published")
    newest = db.scalar(
        select(func.max(Round.published_sequence)).where(Round.series_id == round_.series_id)
    )
    if round_.published_sequence != newest:
        raise PublicationError("only the most recently published round may be unpublished")
    publication = db.scalar(
        select(Publication).where(Publication.round_id == round_id).with_for_update()
    )
    if publication is None:
        raise PublicationError("publication not found")
    if publication.is_imported:
        raise PublicationError("historically imported playlists cannot be retired")
    publication.state = PublicationState.UNPUBLISHING
    publication.retirement_requested = True
    round_.status = RoundStatus.UNPUBLISHING
    return publication


def import_historical_playlist(
    db: Session,
    series_id: uuid.UUID,
    publisher_account_id: uuid.UUID,
    spotify_playlist_id: str,
    opens_at: datetime,
    closes_at: datetime,
    published_at: datetime,
    actor_id: uuid.UUID,
    title: str | None = None,
) -> Round:
    """Create immutable local history from an existing, accessible Spotify playlist."""
    series = db.scalar(select(Series).where(Series.id == series_id).with_for_update())
    if series is None:
        raise PublicationError("series not found")
    if db.scalar(select(Publication.id).where(Publication.spotify_playlist_id == spotify_playlist_id)):
        raise PublicationError("Spotify playlist has already been imported or published")
    publisher = db.get(ExternalAccount, publisher_account_id)
    if (
        publisher is None
        or publisher.provider is not ExternalProvider.SPOTIFY
        or not publisher.is_active
        or publisher.user_id != actor_id
    ):
        raise PublicationError("a connected Spotify publisher is required")
    try:
        snapshot = spotify.playlist_snapshot(
            get_spotify_access_token(db, publisher.id), spotify_playlist_id
        )
    except (httpx.HTTPError, spotify.SpotifyError, ValueError, json.JSONDecodeError) as error:
        raise PublicationError("Spotify playlist could not be imported") from error
    sequence = (
        db.scalar(select(func.max(Round.published_sequence)).where(Round.series_id == series.id))
        or 0
    ) + 1
    round_ = Round(
        series_id=series.id,
        title=(title or str(snapshot["name"]))[:200],
        timezone=series.timezone,
        submission_limit=0,
        opens_at=opens_at,
        closes_at=closes_at,
        publish_at=published_at,
        status=RoundStatus.PUBLISHED,
        publisher_account_id=publisher.id,
        policy_snapshot=[],
        published_sequence=sequence,
    )
    db.add(round_)
    db.flush()
    publication = Publication(
        round_id=round_.id,
        publisher_account_id=publisher.id,
        state=PublicationState.PUBLISHED,
        spotify_playlist_id=spotify_playlist_id,
        idempotency_key=str(uuid.uuid4()),
        is_imported=True,
        published_at=published_at,
    )
    db.add(publication)
    db.flush()
    for position, raw_track in enumerate(snapshot["items"], start=1):
        track = _import_track(db, raw_track)
        db.add(
            PublicationItem(
                publication_id=publication.id,
                submission_id=None,
                track_id=track.id,
                contributor_id=None,
                position=position,
                published_at=published_at,
            )
        )
    db.add(
        AuditEvent(
            actor_id=actor_id,
            action="publication.imported",
            target_type="publication",
            target_id=publication.id,
            details={"roundId": str(round_.id), "playlistId": spotify_playlist_id},
        )
    )
    return round_


def execute_publication(db: Session, publication_id: uuid.UUID) -> None:
    """Perform a retry-safe remote publish, committing playlist identity before item writes."""
    publication = db.scalar(
        select(Publication).where(Publication.id == publication_id).with_for_update()
    )
    if publication is None or publication.state not in {
        PublicationState.PUBLISHING,
        PublicationState.FAILED,
    }:
        return
    round_ = db.get(Round, publication.round_id)
    account = db.get(ExternalAccount, publication.publisher_account_id)
    if round_ is None or account is None:
        _fail(db, publication, round_, "publication prerequisites are unavailable")
        return
    try:
        token = get_spotify_access_token(db, account.id)
        if publication.spotify_playlist_id is None:
            publication.spotify_playlist_id = spotify.create_playlist(
                token, account.provider_subject, round_.title, "Published by Music Rounds"
            )
            publication.attempt_count += 1
            db.commit()
        for item_batch in _unpublished_item_batches(db, publication.id):
            spotify.add_items(
                token,
                publication.spotify_playlist_id,
                [uri for _, uri in item_batch],
            )
            completed_at = datetime.now(UTC)
            for item, _ in item_batch:
                item.published_at = completed_at
            # This checkpoint is what makes a later retry resume from the first
            # unrecorded batch rather than adding the whole snapshot again.
            db.commit()
        mark_published(db, publication.id, publication.spotify_playlist_id)
        publication.published_at = datetime.now(UTC)
        publication.last_error = None
        db.add(
            AuditEvent(
                actor_id=None,
                action="publication.published",
                target_type="publication",
                target_id=publication.id,
                details={"roundId": str(round_.id), "playlistId": publication.spotify_playlist_id},
            )
        )
        db.commit()
    except (httpx.HTTPError, spotify.SpotifyError, ValueError, json.JSONDecodeError):
        _fail(db, publication, round_, "Spotify publication failed")


def execute_retirement(db: Session, publication_id: uuid.UUID) -> None:
    publication = db.scalar(
        select(Publication).where(Publication.id == publication_id).with_for_update()
    )
    if publication is None or publication.state != PublicationState.UNPUBLISHING:
        return
    round_ = db.get(Round, publication.round_id)
    if round_ is None or not publication.spotify_playlist_id:
        _fail(db, publication, round_, "publication cannot be retired")
        return
    try:
        spotify.retire_playlist(
            get_spotify_access_token(db, publication.publisher_account_id),
            publication.spotify_playlist_id,
            _publication_uris(db, publication.id),
        )
        publication.state = PublicationState.UNPUBLISHED
        publication.unpublished_at = datetime.now(UTC)
        round_.status = RoundStatus.CLOSED
        db.add(
            AuditEvent(
                actor_id=None,
                action="publication.unpublished",
                target_type="publication",
                target_id=publication.id,
                details={"roundId": str(round_.id), "playlistId": publication.spotify_playlist_id},
            )
        )
        db.commit()
    except (httpx.HTTPError, spotify.SpotifyError, ValueError, json.JSONDecodeError):
        _fail(db, publication, round_, "Spotify playlist retirement failed")


def get_spotify_access_token(db: Session, account_id: uuid.UUID) -> str:
    credential = db.scalar(
        select(ExternalCredential).where(ExternalCredential.external_account_id == account_id)
    )
    if credential is None:
        raise ValueError("publisher has no credential")
    settings = get_settings()
    payload = json.loads(
        decrypt(credential.ciphertext, settings.credential_encryption_key.get_secret_value())
    )
    token = payload.get("access_token") if isinstance(payload, dict) else None
    if not isinstance(token, str):
        raise ValueError("publisher credential is malformed")
    if credential.expires_at is not None and credential.expires_at <= datetime.now(UTC):
        refresh_token_value = payload.get("refresh_token") if isinstance(payload, dict) else None
        if not isinstance(refresh_token_value, str):
            raise ValueError("publisher credential needs reauthorization")
        refreshed = spotify.refresh_token(settings, refresh_token_value)
        refreshed.setdefault("refresh_token", refresh_token_value)
        credential.ciphertext = encrypt(
            json.dumps(refreshed), settings.credential_encryption_key.get_secret_value()
        )
        credential.expires_at = spotify.token_expiry(refreshed)
        token = str(refreshed["access_token"])
    return token


def _publication_uris(db: Session, publication_id: uuid.UUID) -> list[str]:
    return list(
        db.scalars(
            select(Track.spotify_uri)
            .join(PublicationItem, PublicationItem.track_id == Track.id)
            .where(PublicationItem.publication_id == publication_id, Track.spotify_uri.is_not(None))
            .order_by(PublicationItem.position)
        )
    )


def _import_track(db: Session, raw_track: dict[str, object]) -> Track:
    spotify_track_id = raw_track.get("id")
    if not isinstance(spotify_track_id, str):
        raise PublicationError("Spotify playlist included a malformed track")
    track = db.scalar(select(Track).where(Track.spotify_track_id == spotify_track_id))
    if track is not None:
        return track
    artists = raw_track.get("artists")
    artist = ", ".join(
        item["name"]
        for item in artists
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    ) if isinstance(artists, list) else "Unknown artist"
    album_data = raw_track.get("album")
    album = album_data.get("name") if isinstance(album_data, dict) else None
    artwork_url = None
    if isinstance(album_data, dict) and isinstance(album_data.get("images"), list):
        images = album_data["images"]
        if images and isinstance(images[0], dict) and isinstance(images[0].get("url"), str):
            artwork_url = images[0]["url"]
    name = raw_track.get("name")
    uri = raw_track.get("uri")
    if not isinstance(name, str) or not isinstance(uri, str):
        raise PublicationError("Spotify playlist included a malformed track")
    track = Track(
        spotify_track_id=spotify_track_id,
        name=name[:500],
        artist=artist[:500],
        album=album[:500] if isinstance(album, str) else None,
        spotify_uri=uri,
        artwork_url=artwork_url,
        provider_metadata={
            "explicit": raw_track.get("explicit") is True,
            "isPlayable": raw_track.get("is_playable") is not False,
        },
    )
    db.add(track)
    db.flush()
    return track


def _unpublished_item_batches(
    db: Session, publication_id: uuid.UUID
) -> list[list[tuple[PublicationItem, str]]]:
    items = list(
        db.execute(
            select(PublicationItem, Track.spotify_uri)
            .join(Track, PublicationItem.track_id == Track.id)
            .where(
                PublicationItem.publication_id == publication_id,
                PublicationItem.published_at.is_(None),
            )
            .order_by(PublicationItem.position)
        )
    )
    if any(uri is None for _, uri in items):
        raise ValueError("publication snapshot contains a track without a Spotify URI")
    return [
        [(item, str(uri)) for item, uri in items[start : start + 100]]
        for start in range(0, len(items), 100)
    ]


def _fail(db: Session, publication: Publication, round_: Round | None, message: str) -> None:
    publication.state = PublicationState.FAILED
    publication.attempt_count += 1
    publication.last_error = message
    if round_ is not None:
        round_.status = RoundStatus.FAILED
    db.commit()
