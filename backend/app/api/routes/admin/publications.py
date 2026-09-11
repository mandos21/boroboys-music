"""Publication commands and their durable progress."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DbSession, get_current_user
from app.api.routes.admin._common import (
    _not_found,
    _require_series_admin,
    router,
)
from app.api.schemas import (
    AdminPublicationCommandResponse,
    AdminPublicationResponse,
)
from app.db.models import (
    AuditEvent,
    Publication,
    PublicationState,
    Round,
    RoundStatus,
    User,
)
from app.services.publications import (
    PublicationError,
    defer_or_fail,
    start_publication,
    start_unpublish,
)
from app.tasks import defer_publication, defer_retirement


class PublishRequest(BaseModel):
    publisher_account_id: uuid.UUID


@router.get("/rounds/{round_id}/publication", response_model=AdminPublicationResponse | None)
def get_publication_status(
    round_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, object] | None:
    """Expose durable publication progress and its audit trail to a series admin."""
    round_ = db.get(Round, round_id)
    if round_ is None:
        raise _not_found("round")
    _require_series_admin(db, user, round_.series_id)
    publication = db.scalar(select(Publication).where(Publication.round_id == round_id))
    if publication is None:
        return None
    events = list(
        db.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.target_type == "publication",
                AuditEvent.target_id == publication.id,
            )
            .order_by(AuditEvent.created_at.desc())
        )
    )
    return {
        "id": str(publication.id),
        "state": publication.state.value,
        "isImported": publication.is_imported,
        "retirementRequested": publication.retirement_requested,
        "spotifyPlaylistId": publication.spotify_playlist_id,
        "attemptCount": publication.attempt_count,
        "lastError": publication.last_error,
        "publishedAt": publication.published_at.isoformat() if publication.published_at else None,
        "unpublishedAt": publication.unpublished_at.isoformat()
        if publication.unpublished_at
        else None,
        "events": [
            {
                "id": str(event.id),
                "action": event.action,
                "createdAt": event.created_at.isoformat(),
            }
            for event in events
        ],
    }


@router.post(
    "/rounds/{round_id}/publish",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AdminPublicationCommandResponse,
)
def publish_round_request(
    round_id: uuid.UUID,
    payload: PublishRequest,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, str]:
    round_ = db.get(Round, round_id)
    if round_ is None:
        raise _not_found("round")
    _require_series_admin(db, user, round_.series_id)
    try:
        publication = start_publication(db, round_id, payload.publisher_account_id, user.id)
        db.commit()
    except PublicationError as error:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    defer_or_fail(db, publication, round_, defer_publication)
    return {"publicationId": str(publication.id), "state": publication.state.value}


@router.post(
    "/rounds/{round_id}/unpublish",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AdminPublicationCommandResponse,
)
def unpublish_round_request(
    round_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, str]:
    round_ = db.get(Round, round_id)
    if round_ is None:
        raise _not_found("round")
    _require_series_admin(db, user, round_.series_id)
    try:
        publication = start_unpublish(db, round_id)
        db.commit()
    except PublicationError as error:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    defer_or_fail(db, publication, round_, defer_retirement)
    return {"publicationId": str(publication.id), "state": publication.state.value}


@router.post(
    "/publications/{publication_id}/retry",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AdminPublicationCommandResponse,
)
def retry_publication(
    publication_id: uuid.UUID,
    db: DbSession,
    user: Annotated[User, Depends(get_current_user)],
) -> dict[str, str]:
    publication = db.get(Publication, publication_id)
    if publication is None:
        raise _not_found("publication")
    round_ = db.get(Round, publication.round_id)
    if round_ is None:
        raise _not_found("round")
    _require_series_admin(db, user, round_.series_id)
    if not _is_retryable(publication):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="publication is not retryable"
        )
    if publication.retirement_requested:
        publication.state = PublicationState.UNPUBLISHING
        round_.status = RoundStatus.UNPUBLISHING
        defer = defer_retirement
    else:
        publication.state = PublicationState.PUBLISHING
        round_.status = RoundStatus.PUBLISHING
        defer = defer_publication
    # The previous failure is no longer the current state of this
    # publication, so it must not keep being reported as one.
    publication.last_error = None
    db.commit()
    defer_or_fail(db, publication, round_, defer)
    return {"publicationId": str(publication.id), "state": publication.state.value}


def _is_retryable(publication: Publication) -> bool:
    """Failed publications, plus in-progress ones whose worker lease has lapsed.

    A worker that died without reaching the failure path leaves the row in
    `publishing`/`unpublishing` with an expired lease and nothing to re-queue
    it. Re-queuing is safe because execution re-claims the lease and resumes
    from the last committed batch.
    """
    if publication.state is PublicationState.FAILED:
        return True
    if publication.state not in {PublicationState.PUBLISHING, PublicationState.UNPUBLISHING}:
        return False
    lease = publication.execution_lease_expires_at
    return lease is None or lease <= datetime.now(UTC)
