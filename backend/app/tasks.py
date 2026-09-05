"""Procrastinate task registry.

Phase 0 intentionally exposes only the scheduler reconciliation task. Domain tasks
are added with their durable, idempotent domain state in later phases.
"""
from __future__ import annotations

from procrastinate import App, PsycopgConnector

from app.core.config import get_settings

settings = get_settings()
app = App(connector=PsycopgConnector(conninfo=settings.procrastinate_database_url))


@app.periodic(cron="* * * * *", queue="scheduling")
@app.task(queue="scheduling", queueing_lock="reconcile-schedules")
async def reconcile_schedules(timestamp: int) -> None:
    """Reconcile dynamic round plans; implemented with the round domain in Phase 1."""

    del timestamp
