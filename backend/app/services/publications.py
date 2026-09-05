"""Durable publication snapshots and constrained state transitions."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Publication,
    PublicationItem,
    PublicationState,
    Round,
    RoundStatus,
    Submission,
    SubmissionStatus,
)
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
