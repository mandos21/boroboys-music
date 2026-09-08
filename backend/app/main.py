from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from secrets import token_hex
from time import perf_counter

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Histogram, make_asgi_app

from app.api.router import api_router
from app.core.config import get_settings
from app.db.models import WorkerHeartbeat
from app.db.session import get_session_factory
from app.services.worker_health import HEARTBEAT_NAME
from app.tasks import app as task_app

HTTP_REQUESTS = Counter(
    "music_rounds_http_requests_total",
    "HTTP responses served by Music Rounds.",
    ["method", "path", "status"],
)
HTTP_DURATION = Histogram(
    "music_rounds_http_request_duration_seconds",
    "Time spent serving Music Rounds HTTP requests.",
    ["method", "path"],
)
LOGGER = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Keep the task client available for request handlers that defer durable jobs."""
    task_app.open()
    try:
        yield
    finally:
        task_app.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=f"{settings.app_name} API",
        version="0.1.0",
        docs_url="/api/docs" if settings.app_env != "production" else None,
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(settings.app_base_url).rstrip("/")],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
    )
    app.include_router(api_router)
    app.mount("/metrics", make_asgi_app())

    @app.middleware("http")
    async def record_request_metrics(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        started = perf_counter()
        path = request.url.path if request.url.path in {"/api/v1/health", "/metrics"} else "other"
        request_id = token_hex(12)
        try:
            response = await call_next(request)
        except Exception:
            LOGGER.exception(
                "http_request_failed request_id=%s method=%s path=%s",
                request_id,
                request.method,
                path,
            )
            raise
        elapsed = perf_counter() - started
        HTTP_REQUESTS.labels(request.method, path, response.status_code).inc()
        HTTP_DURATION.labels(request.method, path).observe(elapsed)
        response.headers["X-Request-ID"] = request_id
        # Do not log URLs, query strings, cookies, bodies, or authorization data.
        LOGGER.info(
            "http_request request_id=%s method=%s path=%s status=%s duration_ms=%.1f",
            request_id,
            request.method,
            path,
            response.status_code,
            elapsed * 1_000,
        )
        return response

    @app.get("/api/v1/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "timestamp": datetime.now(UTC).isoformat()}

    @app.get("/api/v1/health/worker", tags=["health"])
    def worker_health() -> Response:
        with get_session_factory()() as db:
            heartbeat = db.get(WorkerHeartbeat, HEARTBEAT_NAME)
        now = datetime.now(UTC)
        if heartbeat is None or heartbeat.observed_at < now - timedelta(minutes=2):
            return Response(
                content='{"status":"degraded","detail":"worker heartbeat is stale"}',
                status_code=503,
                media_type="application/json",
            )
        return Response(
            content=(
                '{"status":"ok","observedAt":"'
                f"{heartbeat.observed_at.isoformat()}"
                '"}'
            ),
            media_type="application/json",
        )

    return app


app = create_app()
