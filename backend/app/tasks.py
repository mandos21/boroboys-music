"""Procrastinate task registry.

Phase 0 intentionally exposes only the scheduler reconciliation task. Domain tasks
are added with their durable, idempotent domain state in later phases.
"""

from __future__ import annotations

import uuid

from procrastinate import App, PsycopgConnector

from app.core.config import get_settings
from app.db.session import get_session_factory
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


@app.task(queue="publishing", queueing_lock="publication-{publication_id}")
async def publish_round(publication_id: str) -> None:
    with get_session_factory()() as db:
        execute_publication(db, uuid.UUID(publication_id))


@app.task(queue="publishing", queueing_lock="retirement-{publication_id}")
async def retire_round(publication_id: str) -> None:
    with get_session_factory()() as db:
        execute_retirement(db, uuid.UUID(publication_id))
