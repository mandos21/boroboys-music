from fastapi import APIRouter

from app.api.routes import admin, auth, health, playlists, setup, submissions, tracks, users

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(health.router, tags=["health"])
api_router.include_router(setup.router, tags=["setup"])
api_router.include_router(auth.router, tags=["auth"])
api_router.include_router(users.router, tags=["users"])
api_router.include_router(tracks.router, tags=["tracks"])
api_router.include_router(submissions.router, tags=["submissions"])
api_router.include_router(playlists.router, tags=["playlists"])
api_router.include_router(admin.router, tags=["admin"])
