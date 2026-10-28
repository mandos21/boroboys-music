"""Procrastinate task registry and the defer helpers its callers use.

Periodic tasks reconcile timestamp-driven state: round transitions and due
publications, worker liveness, and expiry of short-lived auth state. Domain
tasks - publishing, retirement, evidence refresh - are deferred by the API and
are idempotent, because Procrastinate may run one more than once.

Every task is a plain function on purpose. The work inside is blocking -
synchronous SQLAlchemy, httpx and SMTP - and Procrastinate runs a sync task in
a worker thread, whereas an `async def` task would block the worker's event
loop for the duration of a Spotify publish and hold up the heartbeat with it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from procrastinate import App, PsycopgConnector
from procrastinate.exceptions import AlreadyEnqueued
from sqlalchemy import and_, func, or_, select

from app.core.config import get_settings
from app.db.models import Publication, PublicationState, Round, Submission, SubmissionStatus, Track
from app.db.session import get_session_factory
from app.services.auth_cleanup import purge_expired_auth_state
from app.services.evidence import refresh_round_evidence
from app.services.lifecycle import reconcile_rounds
from app.services.notification_rules import collect_due, deliver
from app.services.publications import (
    defer_or_fail,
    execute_publication,
    execute_retirement,
    start_due_publications,
)
from app.services.track_metadata import refresh_track_genres
from app.services.worker_health import record_heartbeat

settings = get_settings()
app = App(connector=PsycopgConnector(conninfo=settings.procrastinate_database_url))


@app.periodic(cron="* * * * *", queue="scheduling")
@app.task(queue="scheduling", queueing_lock="reconcile-schedules")
def reconcile_schedules(timestamp: int) -> None:
    """Reconcile timestamp-driven state after normal operation or worker downtime.

    Closing and publishing are one pass because they are sequential: a round has
    to be closed before its publication time can apply to it. Running them
    together lets a round that closed during downtime still publish immediately.
    """

    del timestamp
    with get_session_factory()() as db:
        reconcile_rounds(db)
        delivery_ids = collect_due(db)
        db.commit()
        for delivery_id in delivery_ids:
            defer_notification(str(delivery_id))
        for publication_id in start_due_publications(db):
            publication = db.get(Publication, publication_id)
            round_ = db.get(Round, publication.round_id) if publication else None
            if publication is None or round_ is None:  # pragma: no cover - just committed
                continue
            defer_or_fail(db, publication, round_, defer_publication)


@app.periodic(cron="* * * * *", queue="scheduling")
@app.task(queue="scheduling", queueing_lock="worker-heartbeat")
def record_worker_heartbeat(timestamp: int) -> None:
    """Provide an independently queryable worker liveness signal every minute."""

    del timestamp
    with get_session_factory()() as db:
        record_heartbeat(db)
        db.commit()


@app.periodic(cron="15 3 * * *", queue="scheduling")
@app.task(queue="scheduling", queueing_lock="purge-auth-state")
def purge_auth_state(timestamp: int) -> None:
    """Keep expired opaque sessions and short-lived OAuth state bounded."""

    del timestamp
    with get_session_factory()() as db:
        purge_expired_auth_state(db)
        db.commit()


@app.periodic(cron="18 * * * *", queue="scheduling")
@app.task(queue="scheduling", queueing_lock="backfill-track-award-metadata")
def backfill_track_award_metadata(timestamp: int) -> None:
    """Queue a bounded batch of old published tracks for listener/genre enrichment."""
    del timestamp
    if not settings.lastfm_api_key:
        return
    retry_before = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    with get_session_factory()() as db:
        track_ids = list(
            db.scalars(
                select(Track.id)
                .join(Submission, Submission.track_id == Track.id)
                .join(Publication, Publication.round_id == Submission.round_id)
                .where(
                    Submission.status == SubmissionStatus.ACCEPTED,
                    Publication.published_at.is_not(None),
                    or_(
                        ~Track.provider_metadata.has_key("lastfmTrackListenersCheckedAt"),
                        and_(
                            Track.provider_metadata["lastfmTrackListenersStatus"].astext == "retry",
                            Track.provider_metadata["lastfmTrackListenersCheckedAt"].astext
                            < retry_before,
                        ),
                        ~Track.provider_metadata.has_key("genreEnrichmentStatus"),
                        and_(
                            Track.provider_metadata["genreEnrichmentStatus"].astext == "incomplete",
                            Track.provider_metadata["genreEnrichmentCheckedAt"].astext
                            < retry_before,
                        ),
                    ),
                )
                .group_by(Track.id)
                .order_by(func.max(Publication.published_at).desc(), Track.id)
                .limit(40)
            )
        )
    for track_id in track_ids:
        defer_track_genre_enrichment(str(track_id))


@app.task(queue="publishing")
def publish_round(publication_id: str) -> None:
    with get_session_factory()() as db:
        was_published = (
            db.scalar(select(Publication.state).where(Publication.id == uuid.UUID(publication_id)))
            is PublicationState.PUBLISHED
        )
        execute_publication(db, uuid.UUID(publication_id))
        publication = db.get(Publication, uuid.UUID(publication_id))
        if (
            not was_published
            and publication is not None
            and publication.state is PublicationState.PUBLISHED
        ):
            defer_round_published_notification(str(publication.round_id))
            track_ids = set(
                db.scalars(
                    select(Submission.track_id).where(
                        Submission.round_id == publication.round_id,
                        Submission.status == SubmissionStatus.ACCEPTED,
                    )
                )
            )
            for track_id in track_ids:
                defer_track_genre_enrichment(str(track_id))


@app.task(queue="publishing")
def retire_round(publication_id: str) -> None:
    with get_session_factory()() as db:
        execute_retirement(db, uuid.UUID(publication_id))


@app.task(queue="evidence")
def refresh_evidence(round_id: str, track_id: str) -> None:
    with get_session_factory()() as db:
        refresh_round_evidence(db, round_id, track_id)


@app.task(queue="metadata")
def enrich_track_genres(track_id: str) -> None:
    with get_session_factory()() as db:
        refresh_track_genres(db, uuid.UUID(track_id))


@app.task(queue="notifications")
def send_notification(delivery_id: str) -> None:
    with get_session_factory()() as db:
        deliver(db, uuid.UUID(delivery_id))


def queue_due_notifications() -> None:
    with get_session_factory()() as db:
        ids = collect_due(db)
        db.commit()
    for delivery_id in ids:
        defer_notification(str(delivery_id))


# Retain task names for jobs queued before the migration, but route them
# through the new ledger so they cannot bypass series settings or deduplication.
@app.task(queue="notifications")
def send_reminder(round_id: str, window: str) -> None:
    queue_due_notifications()


@app.task(queue="notifications")
def notify_published(round_id: str) -> None:
    queue_due_notifications()


@app.task(queue="notifications")
def notify_opened(round_id: str) -> None:
    queue_due_notifications()


def defer_notification(delivery_id: str) -> None:
    _defer_coalesced(send_notification, f"notification:{delivery_id}", {"delivery_id": delivery_id})


def defer_publication(publication_id: str) -> None:
    _defer_coalesced(
        publish_round, f"publication:{publication_id}", {"publication_id": publication_id}
    )


def defer_retirement(publication_id: str) -> None:
    _defer_coalesced(
        retire_round, f"retirement:{publication_id}", {"publication_id": publication_id}
    )


def defer_evidence_refresh(round_id: str, track_id: str) -> None:
    _defer_coalesced(
        refresh_evidence,
        f"evidence:{round_id}:{track_id}",
        {"round_id": round_id, "track_id": track_id},
    )


def defer_round_published_notification(round_id: str) -> None:
    _defer_coalesced(notify_published, f"round-published:{round_id}", {"round_id": round_id})


def defer_track_genre_enrichment(track_id: str) -> None:
    _defer_coalesced(enrich_track_genres, f"track-genres:{track_id}", {"track_id": track_id})


def _defer_coalesced(task: Any, queueing_lock: str, task_kwargs: dict[str, str]) -> None:
    """A duplicate pending refresh is already the requested work, not an API error."""
    try:
        task.configure(queueing_lock=queueing_lock, task_kwargs=task_kwargs).defer()
    except AlreadyEnqueued:
        pass
