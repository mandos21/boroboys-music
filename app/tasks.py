"""Scheduler entry points for recurring background jobs."""
from __future__ import annotations

from datetime import date
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from loguru import logger

from app.config import get_settings
from app.services.playlist_manager import PlaylistManager


scheduler = BackgroundScheduler(timezone="UTC")


def _current_month() -> date:
    today = date.today()
    return today.replace(day=1)


def schedule_monthly_playlist_finalization(
    manager: PlaylistManager,
    *,
    spotify_owner_id: Optional[str],
) -> None:
    settings = get_settings()
    if not settings.enable_scheduler:
        logger.info("Scheduler disabled via configuration; skipping job setup")
        return

    def _finalize_job() -> None:
        logger.info("Running scheduled playlist finalization job")
        manager.finalize_month(_current_month(), spotify_owner_id=spotify_owner_id)

    scheduler.add_job(
        _finalize_job,
        trigger="cron",
        day=1,
        hour=1,
        minute=0,
        id="monthly_playlist_finalization",
        replace_existing=True,
    )
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started")


def shutdown_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Scheduler shutdown complete")