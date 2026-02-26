import json
from pathlib import Path
from typing import Optional

import aiosqlite

from models import Film, StreamingPlatform

DB_PATH = Path("data/watchlist.db")


async def init_db(db_path: Path = DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS films (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                letterboxd_slug     TEXT UNIQUE NOT NULL,
                title               TEXT NOT NULL,
                year                INTEGER,
                tmdb_id             INTEGER,
                tmdb_status         TEXT DEFAULT 'pending',
                poster_url          TEXT,
                overview            TEXT,
                runtime_minutes     INTEGER,
                original_language   TEXT,
                genres              TEXT,
                streaming_platforms TEXT,
                watch_link          TEXT,
                country             TEXT,
                last_checked        TEXT,
                source              TEXT DEFAULT 'letterboxd'
            )
            """
        )
        # Safe migration: add new columns if they don't exist yet (for existing installs)
        for col, definition in [
            ("overview", "TEXT"),
            ("runtime_minutes", "INTEGER"),
            ("original_language", "TEXT"),
            ("genres", "TEXT"),
            ("watch_link", "TEXT"),
        ]:
            try:
                await db.execute(f"ALTER TABLE films ADD COLUMN {col} {definition}")
            except Exception:
                pass  # Column already exists
        await db.commit()


async def upsert_film(film: Film, db_path: Path = DB_PATH) -> None:
    platforms_json = json.dumps([p.model_dump() for p in film.streaming_platforms])
    genres_json = json.dumps(film.genres)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO films
                (letterboxd_slug, title, year, tmdb_id, tmdb_status,
                 poster_url, overview, runtime_minutes, original_language,
                 genres, streaming_platforms, watch_link,
                 country, last_checked, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(letterboxd_slug) DO UPDATE SET
                title               = excluded.title,
                year                = excluded.year,
                tmdb_id             = excluded.tmdb_id,
                tmdb_status         = excluded.tmdb_status,
                poster_url          = excluded.poster_url,
                overview            = excluded.overview,
                runtime_minutes     = excluded.runtime_minutes,
                original_language   = excluded.original_language,
                genres              = excluded.genres,
                streaming_platforms = excluded.streaming_platforms,
                watch_link          = excluded.watch_link,
                country             = excluded.country,
                last_checked        = excluded.last_checked,
                source              = excluded.source
            """,
            (
                film.letterboxd_slug,
                film.title,
                film.year,
                film.tmdb_id,
                film.tmdb_status,
                film.poster_url,
                film.overview,
                film.runtime_minutes,
                film.original_language,
                genres_json,
                platforms_json,
                film.watch_link,
                film.country,
                film.last_checked,
                film.source,
            ),
        )
        await db.commit()


async def get_all_films(db_path: Path = DB_PATH) -> list[Film]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM films ORDER BY title") as cursor:
            rows = await cursor.fetchall()
    return [_row_to_film(row) for row in rows]


async def get_last_updated(db_path: Path = DB_PATH) -> Optional[str]:
    async with aiosqlite.connect(db_path) as db:
        async with db.execute("SELECT MAX(last_checked) FROM films") as cursor:
            row = await cursor.fetchone()
    return row[0] if row else None


def _row_to_film(row: aiosqlite.Row) -> Film:
    platforms_raw = row["streaming_platforms"]
    platforms = (
        [StreamingPlatform(**p) for p in json.loads(platforms_raw)] if platforms_raw else []
    )
    genres_raw = row["genres"]
    genres = json.loads(genres_raw) if genres_raw else []
    return Film(
        id=row["id"],
        letterboxd_slug=row["letterboxd_slug"],
        title=row["title"],
        year=row["year"],
        tmdb_id=row["tmdb_id"],
        tmdb_status=row["tmdb_status"],
        poster_url=row["poster_url"],
        overview=row["overview"],
        runtime_minutes=row["runtime_minutes"],
        original_language=row["original_language"],
        genres=genres,
        streaming_platforms=platforms,
        watch_link=row["watch_link"],
        country=row["country"],
        last_checked=row["last_checked"],
        source=row["source"],
    )
