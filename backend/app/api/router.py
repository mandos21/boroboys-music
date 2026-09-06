"""Versioned API route composition."""

from fastapi import APIRouter

from app.api.routes.admin import router as admin_router
from app.api.routes.auth import router as auth_router
from app.api.routes.connections import router as connections_router
from app.api.routes.rounds import router as rounds_router
from app.api.routes.series import router as series_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
api_router.include_router(admin_router)
api_router.include_router(connections_router)
api_router.include_router(rounds_router)
api_router.include_router(series_router)
