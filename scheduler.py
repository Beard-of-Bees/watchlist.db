import asyncio
import logging
from pathlib import Path
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler

import database
from scraper import scrape_watchlist
from tmdb import enrich_films

logger = logging.getLogger(__name__)

_refresh_lock = asyncio.Lock()
_refresh_state: dict[str, bool] = {"is_refreshing": False}
_scheduler: Optional[AsyncIOScheduler] = None


async def run_refresh(
    username: str,
    tmdb_api_key: str,
    country: str,
    db_path: Path = database.DB_PATH,
) -> bool:
    """
    Run the full scrape -> enrich -> store pipeline.
    Returns True if refresh ran, False if one was already in progress.
    """
    if _refresh_state["is_refreshing"]:
        logger.info("Refresh already in progress, skipping.")
        return False

    async with _refresh_lock:
        if _refresh_state["is_refreshing"]:
            return False
        _refresh_state["is_refreshing"] = True

    try:
        logger.info("Starting refresh for user: %s", username)
        scraped = await scrape_watchlist(username)
        logger.info("Scraped %d films from Letterboxd", len(scraped))

        enriched = await enrich_films(tmdb_api_key, country, scraped)
        logger.info("Enriched %d films from TMDB", len(enriched))

        for film in enriched.values():
            await database.upsert_film(film, db_path)
        await database.delete_films_not_in_watchlist(
            [film.slug for film in scraped],
            db_path,
        )

        logger.info("Refresh complete.")
        return True
    finally:
        _refresh_state["is_refreshing"] = False


def get_refresh_state() -> bool:
    return _refresh_state["is_refreshing"]


def start_scheduler(username: str, tmdb_api_key: str, country: str, cron_expr: str) -> None:
    """Create and start the APScheduler with the refresh job."""
    global _scheduler

    minute, hour, day, month, day_of_week = cron_expr.split()

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        run_refresh,
        "cron",
        args=[username, tmdb_api_key, country],
        minute=minute,
        hour=hour,
        day=day,
        month=month,
        day_of_week=day_of_week,
    )
    _scheduler.start()
    logger.info("Scheduler started. Cron: %s", cron_expr)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown()
        _scheduler = None
