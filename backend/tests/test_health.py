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
    """Uses a real session: the endpoint reads on its own connection.

    The heartbeat has to be genuinely committed for the request handler to see
    it, so this test cannot use the isolated `db` fixture. The row is a
    singleton the worker overwrites anyway, so it leaves nothing accumulating.
    """
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


def test_openapi_and_docs_are_not_served_in_production(monkeypatch: object) -> None:
    import pytest

    from app import main
    from app.core.config import Settings

    production = Settings(
        app_env="production",
        app_base_url="https://music.example.test",
        credential_encryption_key="credential-key",
    )
    assert isinstance(monkeypatch, pytest.MonkeyPatch)
    monkeypatch.setattr(main, "get_settings", lambda: production)

    with TestClient(main.create_app()) as client:
        assert client.get("/api/openapi.json").status_code == 404
        assert client.get("/api/docs").status_code == 404
    # The contract generator does not go through HTTP, so it still works.
    assert "/api/v1/health" in main.create_app().openapi()["paths"]


def test_admin_reads_need_a_session_but_not_a_csrf_token() -> None:
    """The router-wide CSRF guard applies to writes; a GET is not a state change."""
    import uuid

    from app.api.deps import require_csrf_for_writes
    from app.core.security import hash_secret, new_secret
    from app.db.models import PlatformRole, ServerSession, User
    from app.main import create_app

    token = new_secret()
    with get_session_factory()() as db:
        user = User(
            oidc_issuer="https://issuer.test",
            oidc_subject=f"csrf-{uuid.uuid4().hex[:8]}",
            platform_role=PlatformRole.ADMIN,
        )
        db.add(user)
        db.flush()
        db.add(
            ServerSession(
                user_id=user.id,
                token_hash=hash_secret(token),
                csrf_secret_hash=hash_secret(new_secret()),
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        db.commit()

    app = create_app()
    assert any(
        dependency.dependency is require_csrf_for_writes
        for route in app.routes
        if getattr(route, "path", "").startswith("/api/v1/admin/")
        for dependency in getattr(route, "dependencies", [])
    )
    with TestClient(app) as client:
        client.cookies.set("music_rounds_session", token)
        assert client.get("/api/v1/admin/series").status_code == 200
        assert client.post("/api/v1/admin/series", json={}).status_code == 403
