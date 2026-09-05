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
    ExternalAccount,
    ExternalCredential,
    Publication,
    PublicationItem,
    PublicationState,
    Round,
    RoundStatus,
    Submission,
    SubmissionStatus,
    Track,
)
from app.services import spotify
from app.services.lifecycle import create_rolling_successor


class PublicationError(Exception):
    pass


def start_publication(
    db: Session, round_id: uuid.UUID, publisher_account_id: uuid.UUID
) -> Publication:
    round_ = db.scalar(select(Round).where(Round.id == round_id).with_for_update())
    if round_ is None or round_.status is not RoundStatus.CLOSED:
        raise PublicationError("round must be closed before publication")
    if db.scalar(select(Publication).where(Publication.round_id == round_id)):
        raise PublicationError("round already has a publication")
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
    create_rolling_successor(db, round_)
    return publication


def start_unpublish(db: Session, round_id: uuid.UUID) -> Publication:
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
    publication.state = PublicationState.UNPUBLISHING
    round_.status = RoundStatus.UNPUBLISHING
    return publication


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
        token = _access_token(db, account.id)
        if publication.spotify_playlist_id is None:
            publication.spotify_playlist_id = spotify.create_playlist(
                token, account.provider_subject, round_.title, "Published by Music Rounds"
            )
            publication.attempt_count += 1
            db.commit()
        uris = _publication_uris(db, publication.id)
        spotify.add_items(token, publication.spotify_playlist_id, uris)
        mark_published(db, publication.id, publication.spotify_playlist_id)
        publication.published_at = datetime.now(UTC)
        publication.last_error = None
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
            _access_token(db, publication.publisher_account_id),
            publication.spotify_playlist_id,
            _publication_uris(db, publication.id),
        )
        publication.state = PublicationState.UNPUBLISHED
        publication.unpublished_at = datetime.now(UTC)
        round_.status = RoundStatus.CLOSED
        db.commit()
    except (httpx.HTTPError, spotify.SpotifyError, ValueError, json.JSONDecodeError):
        _fail(db, publication, round_, "Spotify playlist retirement failed")


def _access_token(db: Session, account_id: uuid.UUID) -> str:
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


def _fail(db: Session, publication: Publication, round_: Round | None, message: str) -> None:
    publication.state = PublicationState.FAILED
    publication.attempt_count += 1
    publication.last_error = message
    if round_ is not None:
        round_.status = RoundStatus.FAILED
    db.commit()
