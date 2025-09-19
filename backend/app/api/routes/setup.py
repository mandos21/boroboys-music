from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.schemas import (
    SetupInitializeRequest,
    SetupResponse,
    SetupStatus,
    SetupUnlockRequest,
)
from app.services import setup_service

router = APIRouter()


@router.get("/setup/status", response_model=SetupStatus)
def read_setup_status() -> SetupStatus:
    return SetupStatus(ready=setup_service.settings_ready(), unlocked=setup_service.setup_unlocked())


@router.post("/setup/unlock", response_model=SetupStatus)
def unlock_setup(payload: SetupUnlockRequest) -> SetupStatus:
    if not setup_service.unlock_setup(payload.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect setup password")
    return SetupStatus(ready=setup_service.settings_ready(), unlocked=True)


@router.post("/setup/initialize", response_model=SetupResponse)
def initialize_application(payload: SetupInitializeRequest) -> SetupResponse:
    config = setup_service.assemble_setup_config(
        database_host=payload.database_host,
        database_port=payload.database_port,
        database_name=payload.database_name,
        database_user=payload.database_user,
        database_password=payload.database_password,
        spotify_client_id=payload.spotify_client_id,
        spotify_client_secret=payload.spotify_client_secret,
        spotify_redirect_uri=payload.spotify_redirect_uri,
        spotify_scope=payload.spotify_scope,
        secret_key=payload.secret_key,
        frontend_redirect_url=payload.frontend_redirect_url,
        log_level=payload.log_level,
        enable_scheduler=payload.enable_scheduler,
        lastfm_api_key=payload.lastfm_api_key,
        lastfm_shared_secret=payload.lastfm_shared_secret,
        lastfm_username=payload.lastfm_username,
        admin_username=payload.admin_username,
        admin_display_name=payload.admin_display_name,
        admin_password=payload.admin_password,
        admin_spotify_id=payload.admin_spotify_id,
        admin_lastfm_username=payload.admin_lastfm_username,
    )
    try:
        setup_service.initialize_application(config, overwrite_env=payload.overwrite_env)
    except FileExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    return SetupResponse(status=SetupStatus(ready=True, unlocked=False))
