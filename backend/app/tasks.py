"""Procrastinate task registry.

Phase 0 intentionally exposes only the scheduler reconciliation task. Domain tasks
are added with their durable, idempotent domain state in later phases.
"""

from __future__ import annotations

from procrastinate import App, PsycopgConnector

from app.core.config import get_settings
from app.db.session import get_session_factory
from app.services.lifecycle import reconcile_rounds

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
