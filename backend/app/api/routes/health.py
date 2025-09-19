from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter

from app.schemas import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok", timestamp=datetime.utcnow())
