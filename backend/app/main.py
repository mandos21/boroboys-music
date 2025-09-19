from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.api import api_router
from app.bootstrap import initialize_database
from app.config import get_settings


def create_app() -> FastAPI:
    app = FastAPI(title="Boro Boys Music API")

    app.add_middleware(
        SessionMiddleware,
        secret_key=os.getenv("SECRET_KEY", "setup-secret"),
        https_only=False,
        same_site="lax",
        max_age=60 * 60 * 24 * 14,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    @app.on_event("startup")
    def ensure_database() -> None:
        try:
            settings = get_settings()
        except Exception:  # pragma: no cover - configuration not ready yet
            return
        initialize_database(settings.database_url)

    @app.get("/")
    async def root() -> dict[str, str]:
        return {"service": "boroboys-music", "status": "online"}

    return app


app = create_app()
