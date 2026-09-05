"""Versioned API route composition."""

from fastapi import APIRouter

from app.api.routes.auth import router as auth_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth_router)
