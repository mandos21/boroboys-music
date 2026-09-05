from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI

from app.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Music Rounds API",
        version="0.1.0",
        docs_url="/api/docs" if settings.app_env != "production" else None,
        openapi_url="/api/openapi.json",
    )

    @app.get("/api/v1/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "timestamp": datetime.now(UTC).isoformat()}

    return app


app = create_app()
