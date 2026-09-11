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
from typing import Any

from procrastinate import App, PsycopgConnector
from procrastinate.exceptions import AlreadyEnqueued
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import Publication, PublicationState, Round
from app.db.session import get_session_factory
from app.services.auth_cleanup import purge_expired_auth_state
from app.services.evidence import refresh_round_evidence
from app.services.lifecycle import reconcile_rounds, start_due_open_announcements
from app.services.notifications import (
    notify_round_opened,
    notify_round_published,
    send_round_reminder,
    start_due_reminders,
)
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
        opened_round_ids = start_due_open_announcements(db)
        due_reminders = start_due_reminders(db)
        db.commit()
        for round_id in opened_round_ids:
            defer_round_opened_notification(str(round_id))
        for round_id, window in due_reminders:
            defer_reminder(str(round_id), window)
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
def send_reminder(round_id: str, window: str) -> None:
    with get_session_factory()() as db:
        send_round_reminder(db, uuid.UUID(round_id), window)


@app.task(queue="notifications")
def notify_published(round_id: str) -> None:
    with get_session_factory()() as db:
        notify_round_published(db, uuid.UUID(round_id))


@app.task(queue="notifications")
def notify_opened(round_id: str) -> None:
    with get_session_factory()() as db:
        notify_round_opened(db, uuid.UUID(round_id))


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


def defer_reminder(round_id: str, window: str) -> None:
    _defer_coalesced(
        send_reminder, f"reminder:{round_id}:{window}", {"round_id": round_id, "window": window}
    )


def defer_round_published_notification(round_id: str) -> None:
    _defer_coalesced(notify_published, f"round-published:{round_id}", {"round_id": round_id})


def defer_round_opened_notification(round_id: str) -> None:
    _defer_coalesced(notify_opened, f"round-opened:{round_id}", {"round_id": round_id})


def defer_track_genre_enrichment(track_id: str) -> None:
    _defer_coalesced(enrich_track_genres, f"track-genres:{track_id}", {"track_id": track_id})


def _defer_coalesced(task: Any, queueing_lock: str, task_kwargs: dict[str, str]) -> None:
    """A duplicate pending refresh is already the requested work, not an API error."""
    try:
        task.configure(queueing_lock=queueing_lock, task_kwargs=task_kwargs).defer()
    except AlreadyEnqueued:
        pass
