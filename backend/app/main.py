from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from time import perf_counter

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Histogram, make_asgi_app

from app.api.router import api_router
from app.core.config import get_settings

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


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Music Rounds API",
        version="0.1.0",
        docs_url="/api/docs" if settings.app_env != "production" else None,
        openapi_url="/api/openapi.json",
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
        response = await call_next(request)
        path = request.url.path if request.url.path in {"/api/v1/health", "/metrics"} else "other"
        HTTP_REQUESTS.labels(request.method, path, response.status_code).inc()
        HTTP_DURATION.labels(request.method, path).observe(perf_counter() - started)
        return response

    @app.get("/api/v1/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "timestamp": datetime.now(UTC).isoformat()}

    return app


app = create_app()
