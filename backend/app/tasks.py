"""Procrastinate task registry.

Phase 0 intentionally exposes only the scheduler reconciliation task. Domain tasks
are added with their durable, idempotent domain state in later phases.
"""

from __future__ import annotations

import uuid
from typing import Any

from procrastinate import App, PsycopgConnector
from procrastinate.exceptions import AlreadyEnqueued

from app.core.config import get_settings
from app.db.models import Publication, Round
from app.db.session import get_session_factory
from app.services.auth_cleanup import purge_expired_auth_state
from app.services.evidence import refresh_round_evidence
from app.services.lifecycle import reconcile_rounds
from app.services.publications import (
    defer_or_fail,
    execute_publication,
    execute_retirement,
    start_due_publications,
)
from app.services.worker_health import record_heartbeat

settings = get_settings()
app = App(connector=PsycopgConnector(conninfo=settings.procrastinate_database_url))


@app.periodic(cron="* * * * *", queue="scheduling")
@app.task(queue="scheduling", queueing_lock="reconcile-schedules")
async def reconcile_schedules(timestamp: int) -> None:
    """Reconcile timestamp-driven state after normal operation or worker downtime.

    Closing and publishing are one pass because they are sequential: a round has
    to be closed before its publication time can apply to it. Running them
    together lets a round that closed during downtime still publish immediately.
    """

    del timestamp
    with get_session_factory()() as db:
        reconcile_rounds(db)
        db.commit()
        for publication_id in start_due_publications(db):
            publication = db.get(Publication, publication_id)
            round_ = db.get(Round, publication.round_id) if publication else None
            if publication is None or round_ is None:  # pragma: no cover - just committed
                continue
            defer_or_fail(db, publication, round_, defer_publication)


@app.periodic(cron="* * * * *", queue="scheduling")
@app.task(queue="scheduling", queueing_lock="worker-heartbeat")
async def record_worker_heartbeat(timestamp: int) -> None:
    """Provide an independently queryable worker liveness signal every minute."""

    del timestamp
    with get_session_factory()() as db:
        record_heartbeat(db)
        db.commit()


@app.periodic(cron="15 3 * * *", queue="scheduling")
@app.task(queue="scheduling", queueing_lock="purge-auth-state")
async def purge_auth_state(timestamp: int) -> None:
    """Keep expired opaque sessions and short-lived OAuth state bounded."""

    del timestamp
    with get_session_factory()() as db:
        purge_expired_auth_state(db)
        db.commit()


@app.task(queue="publishing")
async def publish_round(publication_id: str) -> None:
    with get_session_factory()() as db:
        execute_publication(db, uuid.UUID(publication_id))


@app.task(queue="publishing")
async def retire_round(publication_id: str) -> None:
    with get_session_factory()() as db:
        execute_retirement(db, uuid.UUID(publication_id))


@app.task(queue="evidence")
async def refresh_evidence(round_id: str, track_id: str) -> None:
    with get_session_factory()() as db:
        refresh_round_evidence(db, round_id, track_id)


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


def _defer_coalesced(task: Any, queueing_lock: str, task_kwargs: dict[str, str]) -> None:
    """A duplicate pending refresh is already the requested work, not an API error."""
    try:
        task.configure(queueing_lock=queueing_lock, task_kwargs=task_kwargs).defer()
    except AlreadyEnqueued:
        pass
