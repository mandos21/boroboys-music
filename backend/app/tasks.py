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
from app.db.session import get_session_factory
from app.services.evidence import refresh_round_evidence
from app.services.lifecycle import reconcile_rounds
from app.services.publications import execute_publication, execute_retirement

settings = get_settings()
app = App(connector=PsycopgConnector(conninfo=settings.procrastinate_database_url))


@app.periodic(cron="* * * * *", queue="scheduling")
@app.task(queue="scheduling", queueing_lock="reconcile-schedules")
async def reconcile_schedules(timestamp: int) -> None:
    """Reconcile timestamp-driven state after normal operation or worker downtime."""

    del timestamp
    with get_session_factory()() as db:
        reconcile_rounds(db)
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
