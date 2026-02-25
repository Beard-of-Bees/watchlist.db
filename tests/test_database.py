from models import Film, StreamingPlatform

import database


async def test_init_db_creates_table(tmp_db):
    await database.init_db(tmp_db)
    import aiosqlite

    async with aiosqlite.connect(tmp_db) as db:
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='films'"
        ) as cursor:
            row = await cursor.fetchone()
    assert row is not None


async def test_upsert_and_get_film(tmp_db):
    await database.init_db(tmp_db)
    film = Film(
        letterboxd_slug="oppenheimer-2023",
        title="Oppenheimer",
        year=2023,
        tmdb_id=872585,
        tmdb_status="found",
        poster_url="https://example.com/poster.jpg",
        streaming_platforms=[
            StreamingPlatform(provider_id=8, provider_name="Netflix", logo_path="/n.png")
        ],
        country="GB",
        last_checked="2026-01-01T00:00:00",
    )
    await database.upsert_film(film, tmp_db)

    films = await database.get_all_films(tmp_db)
    assert len(films) == 1
    assert films[0].title == "Oppenheimer"
    assert films[0].tmdb_id == 872585
    assert len(films[0].streaming_platforms) == 1
    assert films[0].streaming_platforms[0].provider_name == "Netflix"


async def test_upsert_is_idempotent(tmp_db):
    await database.init_db(tmp_db)
    film = Film(letterboxd_slug="dune-2021", title="Dune", tmdb_status="pending")
    await database.upsert_film(film, tmp_db)
    film.tmdb_status = "found"
    film.tmdb_id = 438631
    await database.upsert_film(film, tmp_db)

    films = await database.get_all_films(tmp_db)
    assert len(films) == 1
    assert films[0].tmdb_status == "found"
    assert films[0].tmdb_id == 438631


async def test_get_last_updated_returns_none_when_empty(tmp_db):
    await database.init_db(tmp_db)
    result = await database.get_last_updated(tmp_db)
    assert result is None


async def test_get_last_updated_returns_max_timestamp(tmp_db):
    await database.init_db(tmp_db)
    await database.upsert_film(
        Film(letterboxd_slug="film-a", title="A", last_checked="2026-01-01T00:00:00"),
        tmp_db,
    )
    await database.upsert_film(
        Film(letterboxd_slug="film-b", title="B", last_checked="2026-02-01T00:00:00"),
        tmp_db,
    )
    result = await database.get_last_updated(tmp_db)
    assert result == "2026-02-01T00:00:00"
