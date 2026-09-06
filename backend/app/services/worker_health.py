"""Worker liveness storage shared by the task and API processes."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models import WorkerHeartbeat

HEARTBEAT_NAME = "procrastinate"


def record_heartbeat(db: Session, observed_at: datetime | None = None) -> WorkerHeartbeat:
    heartbeat = db.get(WorkerHeartbeat, HEARTBEAT_NAME)
    instant = observed_at or datetime.now(UTC)
    if heartbeat is None:
        heartbeat = WorkerHeartbeat(name=HEARTBEAT_NAME, observed_at=instant)
        db.add(heartbeat)
    else:
        heartbeat.observed_at = instant
    return heartbeat
