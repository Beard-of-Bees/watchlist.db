import asyncio
from unittest.mock import AsyncMock, patch

from models import Film
from scraper import ScrapedFilm


async def test_run_refresh_calls_scraper_and_tmdb(tmp_db):
    import database

    await database.init_db(tmp_db)

    mock_scraped = [ScrapedFilm(slug="oppenheimer-2023", title="Oppenheimer")]
    mock_enriched = {
        "oppenheimer-2023": Film(
            letterboxd_slug="oppenheimer-2023",
            title="Oppenheimer",
            tmdb_status="found",
            tmdb_id=872585,
        )
    }

    with (
        patch("scheduler.scrape_watchlist", new=AsyncMock(return_value=mock_scraped)) as mock_scrape,
        patch("scheduler.enrich_films", new=AsyncMock(return_value=mock_enriched)) as mock_enrich,
    ):
        import scheduler

        await scheduler.run_refresh(
            username="testuser",
            tmdb_api_key="key",
            country="GB",
            db_path=tmp_db,
        )

    mock_scrape.assert_called_once_with("testuser")
    mock_enrich.assert_called_once_with("key", "GB", mock_scraped)

    films = await database.get_all_films(tmp_db)
    assert len(films) == 1
    assert films[0].tmdb_status == "found"


async def test_run_refresh_prevents_concurrent_runs(tmp_db):
    import database
    import scheduler

    await database.init_db(tmp_db)

    async def slow_scrape(username):
        await asyncio.sleep(0.1)
        return []

    with patch("scheduler.scrape_watchlist", new=slow_scrape):
        with patch("scheduler.enrich_films", new=AsyncMock(return_value={})):
            result1, result2 = await asyncio.gather(
                scheduler.run_refresh("u", "k", "GB", tmp_db),
                scheduler.run_refresh("u", "k", "GB", tmp_db),
            )

    assert (result1 is True) != (result2 is True)


def test_get_refresh_state_initial():
    import scheduler

    scheduler._refresh_state["is_refreshing"] = False
    assert scheduler.get_refresh_state() is False
