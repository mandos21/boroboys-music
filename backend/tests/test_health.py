from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.db.session import get_session_factory
from app.main import create_app
from app.services.worker_health import record_heartbeat


def test_health_endpoint_returns_service_status() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["X-Request-ID"].isalnum()
    assert len(response.headers["X-Request-ID"]) == 24


def test_metrics_endpoint_exposes_music_rounds_metrics() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/metrics")

    assert response.status_code == 200
    assert "music_rounds_http_requests_total" in response.text


def test_worker_health_reflects_fresh_and_stale_heartbeats() -> None:
    with get_session_factory()() as db:
        record_heartbeat(db, datetime.now(UTC))
        db.commit()
    with TestClient(create_app()) as client:
        healthy = client.get("/api/v1/health/worker")
    assert healthy.status_code == 200
    assert healthy.json()["status"] == "ok"

    with get_session_factory()() as db:
        record_heartbeat(db, datetime.now(UTC) - timedelta(minutes=3))
        db.commit()
    with TestClient(create_app()) as client:
        stale = client.get("/api/v1/health/worker")
    assert stale.status_code == 503
    assert stale.json()["status"] == "degraded"
