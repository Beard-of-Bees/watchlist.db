# watchlist.db v1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a self-hosted Python web app that scrapes a Letterboxd watchlist, enriches films with TMDB streaming availability, and serves results from a SQLite cache.

**Architecture:** Background APScheduler job scrapes Letterboxd HTML → searches TMDB for each film → fetches watch providers → upserts to SQLite. FastAPI serves cached results via Jinja2 template; a manual refresh endpoint triggers the job on demand.

**Tech Stack:** FastAPI, Jinja2, httpx (async), BeautifulSoup4, aiosqlite, APScheduler 3.x, pydantic-settings, uv/pyproject.toml, Docker Compose.

---

## Pre-flight: Read before starting

- `CLAUDE.md` — architecture decisions, pitfalls, module conventions
- `BRIEF.md` — full v1 scope and out-of-scope items
- `docs/plans/2026-02-25-watchlist-db-v1.md` — this file

Key constraints to keep in mind:
- All Letterboxd scraping logic lives in `scraper.py` ONLY — no scraping code in other modules
- All SQL lives in `database.py` ONLY — no SQL in routes or other modules
- Use `aiosqlite` for all DB access — never bare `sqlite3` in async context
- APScheduler pinned to `3.x` — do not upgrade to 4.x (completely different API)
- `asyncio.Semaphore(10)` wraps all TMDB HTTP calls — do not use bare `asyncio.gather()` without it

---

## Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `tests/__init__.py` (empty)
- Create: `tests/conftest.py`

**Step 1: Create pyproject.toml**

```toml
[project]
name = "watchlist-db"
version = "0.1.0"
description = "Self-hosted Letterboxd watchlist with streaming availability"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "httpx>=0.27.0",
    "beautifulsoup4>=4.12.0",
    "aiosqlite>=0.20.0",
    "apscheduler>=3.10.0,<4.0.0",
    "pydantic-settings>=2.6.0",
    "jinja2>=3.1.0",
    "python-multipart>=0.0.12",
]

[dependency-groups]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "pytest-mock>=3.14.0",
    "respx>=0.21.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

**Step 2: Create .env.example**

```env
LETTERBOXD_USERNAME=your_username
TMDB_API_KEY=your_key_here
COUNTRY=GB
REFRESH_SCHEDULE=0 0 * * 0
```

**Step 3: Create .gitignore**

```
.env
data/
__pycache__/
*.pyc
.pytest_cache/
*.egg-info/
dist/
.venv/
uv.lock
```

**Step 4: Create tests/conftest.py**

```python
import pytest
import pytest_asyncio
import aiosqlite
from pathlib import Path


@pytest.fixture
def tmp_db(tmp_path) -> Path:
    """Returns path to a temporary SQLite database file."""
    return tmp_path / "test.db"
```

**Step 5: Install dependencies**

```bash
uv sync --group dev
```

Expected: packages installed, `uv.lock` created.

**Step 6: Commit**

```bash
git init
git add pyproject.toml .env.example .gitignore tests/__init__.py tests/conftest.py
git commit -m "chore: project scaffolding"
```

---

## Task 2: Pydantic Models

**Files:**
- Create: `models.py`
- Create: `tests/test_models.py`

**Step 1: Write the failing test**

Create `tests/test_models.py`:

```python
from models import Film, StreamingPlatform


def test_film_defaults():
    film = Film(letterboxd_slug="oppenheimer-2023", title="Oppenheimer")
    assert film.tmdb_status == "pending"
    assert film.streaming_platforms == []
    assert film.source == "letterboxd"
    assert film.id is None


def test_streaming_platform():
    p = StreamingPlatform(provider_id=8, provider_name="Netflix")
    assert p.provider_id == 8
    assert p.logo_path is None


def test_film_with_platforms():
    p = StreamingPlatform(provider_id=8, provider_name="Netflix", logo_path="/abc.png")
    film = Film(
        letterboxd_slug="oppenheimer-2023",
        title="Oppenheimer",
        tmdb_id=872585,
        tmdb_status="found",
        streaming_platforms=[p],
    )
    assert len(film.streaming_platforms) == 1
    assert film.streaming_platforms[0].provider_name == "Netflix"
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_models.py -v
```

Expected: `ModuleNotFoundError: No module named 'models'`

**Step 3: Write minimal implementation**

Create `models.py`:

```python
from pydantic import BaseModel
from typing import Optional


class StreamingPlatform(BaseModel):
    provider_id: int
    provider_name: str
    logo_path: Optional[str] = None


class Film(BaseModel):
    id: Optional[int] = None
    letterboxd_slug: str
    title: str
    year: Optional[int] = None
    tmdb_id: Optional[int] = None
    tmdb_status: str = "pending"  # pending | found | not_found | error
    poster_url: Optional[str] = None
    streaming_platforms: list[StreamingPlatform] = []
    country: Optional[str] = None
    last_checked: Optional[str] = None  # ISO timestamp string
    source: str = "letterboxd"
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_models.py -v
```

Expected: 3 tests PASS.

**Step 5: Commit**

```bash
git add models.py tests/test_models.py
git commit -m "feat: add Pydantic models for Film and StreamingPlatform"
```

---

## Task 3: Config

**Files:**
- Create: `config.py`
- Create: `tests/test_config.py`

**Step 1: Write the failing tests**

Create `tests/test_config.py`:

```python
import pytest
from pydantic import ValidationError


def test_valid_config(monkeypatch):
    monkeypatch.setenv("LETTERBOXD_USERNAME", "testuser")
    monkeypatch.setenv("TMDB_API_KEY", "abc123")
    monkeypatch.delenv("COUNTRY", raising=False)
    monkeypatch.delenv("REFRESH_SCHEDULE", raising=False)

    # Import fresh — pydantic-settings reads env at instantiation
    from importlib import import_module, reload
    import config
    reload(config)

    assert config.settings.letterboxd_username == "testuser"
    assert config.settings.tmdb_api_key == "abc123"
    assert config.settings.country == "GB"
    assert config.settings.refresh_schedule == "0 0 * * 0"


def test_missing_required_vars(monkeypatch):
    monkeypatch.delenv("LETTERBOXD_USERNAME", raising=False)
    monkeypatch.delenv("TMDB_API_KEY", raising=False)

    from importlib import reload
    import config

    with pytest.raises((ValidationError, Exception)):
        from config import Settings
        Settings(_env_file=None)
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_config.py -v
```

Expected: `ModuleNotFoundError: No module named 'config'`

**Step 3: Write minimal implementation**

Create `config.py`:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    letterboxd_username: str
    tmdb_api_key: str
    country: str = "GB"
    refresh_schedule: str = "0 0 * * 0"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = Settings()
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_config.py -v
```

Expected: 2 tests PASS.

**Step 5: Commit**

```bash
git add config.py tests/test_config.py
git commit -m "feat: add pydantic-settings config with startup validation"
```

---

## Task 4: Database

**Files:**
- Create: `database.py`
- Create: `tests/test_database.py`

The `tmp_db` fixture (from `conftest.py`) provides a temporary DB path for each test — always pass it as `db_path` to avoid touching the real DB during tests.

**Step 1: Write the failing tests**

Create `tests/test_database.py`:

```python
import pytest
from pathlib import Path
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
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_database.py -v
```

Expected: `ModuleNotFoundError: No module named 'database'`

**Step 3: Write minimal implementation**

Create `database.py`:

```python
import json
import aiosqlite
from pathlib import Path
from typing import Optional
from models import Film, StreamingPlatform

DB_PATH = Path("data/watchlist.db")


async def init_db(db_path: Path = DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS films (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                letterboxd_slug     TEXT UNIQUE NOT NULL,
                title               TEXT NOT NULL,
                year                INTEGER,
                tmdb_id             INTEGER,
                tmdb_status         TEXT DEFAULT 'pending',
                poster_url          TEXT,
                streaming_platforms TEXT,
                country             TEXT,
                last_checked        TEXT,
                source              TEXT DEFAULT 'letterboxd'
            )
        """)
        await db.commit()


async def upsert_film(film: Film, db_path: Path = DB_PATH) -> None:
    platforms_json = json.dumps([p.model_dump() for p in film.streaming_platforms])
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            INSERT INTO films
                (letterboxd_slug, title, year, tmdb_id, tmdb_status,
                 poster_url, streaming_platforms, country, last_checked, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(letterboxd_slug) DO UPDATE SET
                title               = excluded.title,
                year                = excluded.year,
                tmdb_id             = excluded.tmdb_id,
                tmdb_status         = excluded.tmdb_status,
                poster_url          = excluded.poster_url,
                streaming_platforms = excluded.streaming_platforms,
                country             = excluded.country,
                last_checked        = excluded.last_checked,
                source              = excluded.source
        """, (
            film.letterboxd_slug, film.title, film.year, film.tmdb_id,
            film.tmdb_status, film.poster_url, platforms_json,
            film.country, film.last_checked, film.source,
        ))
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


def _row_to_film(row) -> Film:
    platforms_raw = row["streaming_platforms"]
    platforms = (
        [StreamingPlatform(**p) for p in json.loads(platforms_raw)]
        if platforms_raw
        else []
    )
    return Film(
        id=row["id"],
        letterboxd_slug=row["letterboxd_slug"],
        title=row["title"],
        year=row["year"],
        tmdb_id=row["tmdb_id"],
        tmdb_status=row["tmdb_status"],
        poster_url=row["poster_url"],
        streaming_platforms=platforms,
        country=row["country"],
        last_checked=row["last_checked"],
        source=row["source"],
    )
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_database.py -v
```

Expected: 5 tests PASS.

**Step 5: Commit**

```bash
git add database.py tests/test_database.py
git commit -m "feat: add database layer with aiosqlite upsert and query"
```

---

## Task 5: Letterboxd Scraper

**Files:**
- Create: `scraper.py`
- Create: `tests/test_scraper.py`

All scraping logic lives here. Never import from `scraper.py` inside `scraper.py` and never put HTML parsing in any other file.

**Step 1: Write the failing tests**

Letterboxd watchlist page HTML structure (simplified — what we parse):

```html
<ul class="poster-list -p70 -grid film-list clear">
  <li class="poster-container">
    <div class="film-poster" data-film-slug="oppenheimer-2023" data-target-link="/film/oppenheimer-2023/">
      <img src="..." alt="Oppenheimer" class="image" />
    </div>
  </li>
</ul>
<div class="paginate-pages">
  <a class="next" href="/user/watchlist/page/2/">Next</a>
</div>
```

Create `tests/test_scraper.py`:

```python
import pytest
import respx
import httpx
from scraper import scrape_watchlist, _parse_watchlist_page

SINGLE_PAGE_HTML = """
<html><body>
<ul class="poster-list -p70 -grid film-list clear">
  <li class="poster-container">
    <div class="film-poster" data-film-slug="oppenheimer-2023">
      <img alt="Oppenheimer" class="image" />
    </div>
  </li>
  <li class="poster-container">
    <div class="film-poster" data-film-slug="dune-2021">
      <img alt="Dune" class="image" />
    </div>
  </li>
</ul>
</body></html>
"""

PAGINATED_HTML_PAGE_1 = """
<html><body>
<ul class="poster-list -p70 -grid film-list clear">
  <li class="poster-container">
    <div class="film-poster" data-film-slug="oppenheimer-2023">
      <img alt="Oppenheimer" class="image" />
    </div>
  </li>
</ul>
<div class="paginate-pages">
  <a class="next" href="/testuser/watchlist/page/2/">Next</a>
</div>
</body></html>
"""

PAGINATED_HTML_PAGE_2 = """
<html><body>
<ul class="poster-list -p70 -grid film-list clear">
  <li class="poster-container">
    <div class="film-poster" data-film-slug="dune-2021">
      <img alt="Dune" class="image" />
    </div>
  </li>
</ul>
</body></html>
"""


def test_parse_single_page_no_next():
    films, has_next = _parse_watchlist_page(SINGLE_PAGE_HTML)
    assert len(films) == 2
    assert films[0].slug == "oppenheimer-2023"
    assert films[0].title == "Oppenheimer"
    assert films[1].slug == "dune-2021"
    assert has_next is False


def test_parse_page_with_next_link():
    _, has_next = _parse_watchlist_page(PAGINATED_HTML_PAGE_1)
    assert has_next is True


def test_parse_ignores_entries_without_slug():
    html = """
    <ul class="poster-list -p70 -grid film-list clear">
      <li class="poster-container">
        <div class="film-poster">
          <img alt="Unknown" />
        </div>
      </li>
    </ul>
    """
    films, _ = _parse_watchlist_page(html)
    assert films == []


@respx.mock
async def test_scrape_watchlist_single_page():
    respx.get("https://letterboxd.com/testuser/watchlist/page/1/").mock(
        return_value=httpx.Response(200, text=SINGLE_PAGE_HTML)
    )
    films = await scrape_watchlist("testuser", request_delay=0)
    assert len(films) == 2
    assert films[0].slug == "oppenheimer-2023"


@respx.mock
async def test_scrape_watchlist_follows_pagination():
    respx.get("https://letterboxd.com/testuser/watchlist/page/1/").mock(
        return_value=httpx.Response(200, text=PAGINATED_HTML_PAGE_1)
    )
    respx.get("https://letterboxd.com/testuser/watchlist/page/2/").mock(
        return_value=httpx.Response(200, text=PAGINATED_HTML_PAGE_2)
    )
    films = await scrape_watchlist("testuser", request_delay=0)
    assert len(films) == 2
    slugs = [f.slug for f in films]
    assert "oppenheimer-2023" in slugs
    assert "dune-2021" in slugs
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_scraper.py -v
```

Expected: `ModuleNotFoundError: No module named 'scraper'`

**Step 3: Write minimal implementation**

Create `scraper.py`:

```python
import asyncio
from typing import NamedTuple

import httpx
from bs4 import BeautifulSoup

LETTERBOXD_BASE = "https://letterboxd.com"
DEFAULT_REQUEST_DELAY = 1.5


class ScrapedFilm(NamedTuple):
    slug: str
    title: str


async def scrape_watchlist(
    username: str, request_delay: float = DEFAULT_REQUEST_DELAY
) -> list[ScrapedFilm]:
    """Scrape all pages of a public Letterboxd watchlist."""
    films: list[ScrapedFilm] = []
    page = 1

    async with httpx.AsyncClient(
        headers={"User-Agent": "watchlist.db/1.0 (self-hosted)"},
        timeout=30.0,
    ) as client:
        while True:
            url = f"{LETTERBOXD_BASE}/{username}/watchlist/page/{page}/"
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()

            page_films, has_next = _parse_watchlist_page(response.text)
            films.extend(page_films)

            if not has_next:
                break

            page += 1
            await asyncio.sleep(request_delay)

    return films


def _parse_watchlist_page(html: str) -> tuple[list[ScrapedFilm], bool]:
    """Parse one page of watchlist HTML. Returns (films, has_next_page)."""
    soup = BeautifulSoup(html, "html.parser")

    film_posters = soup.select("li.poster-container div.film-poster")
    films: list[ScrapedFilm] = []

    for poster in film_posters:
        slug = poster.get("data-film-slug", "").strip()
        if not slug:
            continue
        img = poster.find("img")
        title = img["alt"] if img and img.get("alt") else slug
        films.append(ScrapedFilm(slug=slug, title=title))

    has_next = soup.select_one("a.next") is not None
    return films, has_next
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_scraper.py -v
```

Expected: 6 tests PASS.

**Step 5: Commit**

```bash
git add scraper.py tests/test_scraper.py
git commit -m "feat: add Letterboxd watchlist scraper with pagination"
```

---

## Task 6: TMDB Client

**Files:**
- Create: `tmdb.py`
- Create: `tests/test_tmdb.py`

TMDB enrichment is a two-step flow per film: (1) search by title → get `tmdb_id`, (2) fetch watch providers + movie details for poster. Both steps run concurrently across films using a shared `asyncio.Semaphore(10)`.

Logo paths from TMDB are relative (e.g. `/abc.png`) — prepend `https://image.tmdb.org/t/p/w45`. Poster paths use `https://image.tmdb.org/t/p/w300`.

Only `flatrate` providers are shown (subscription streaming, not rent/buy).

**Step 1: Write the failing tests**

Create `tests/test_tmdb.py`:

```python
import pytest
import respx
import httpx
from models import StreamingPlatform
from tmdb import search_movie, get_movie_details, enrich_films

TMDB_SEARCH_RESPONSE = {
    "results": [{"id": 872585, "title": "Oppenheimer", "release_date": "2023-07-21"}]
}

TMDB_WATCH_PROVIDERS_RESPONSE = {
    "results": {
        "GB": {
            "flatrate": [
                {"provider_id": 8, "provider_name": "Netflix", "logo_path": "/netflix.png"}
            ]
        }
    }
}

TMDB_MOVIE_DETAILS_RESPONSE = {
    "id": 872585,
    "title": "Oppenheimer",
    "release_date": "2023-07-21",
    "poster_path": "/oppenheimer.jpg",
}

TMDB_EMPTY_SEARCH = {"results": []}


@respx.mock
async def test_search_movie_returns_tmdb_id():
    respx.get("https://api.themoviedb.org/3/search/movie").mock(
        return_value=httpx.Response(200, json=TMDB_SEARCH_RESPONSE)
    )
    async with httpx.AsyncClient() as client:
        tmdb_id = await search_movie(client, "fake_key", "Oppenheimer")
    assert tmdb_id == 872585


@respx.mock
async def test_search_movie_returns_none_when_not_found():
    respx.get("https://api.themoviedb.org/3/search/movie").mock(
        return_value=httpx.Response(200, json=TMDB_EMPTY_SEARCH)
    )
    async with httpx.AsyncClient() as client:
        tmdb_id = await search_movie(client, "fake_key", "Nonexistent Film XYZ")
    assert tmdb_id is None


@respx.mock
async def test_get_movie_details_returns_poster_and_platforms():
    respx.get("https://api.themoviedb.org/3/movie/872585").mock(
        return_value=httpx.Response(200, json=TMDB_MOVIE_DETAILS_RESPONSE)
    )
    respx.get("https://api.themoviedb.org/3/movie/872585/watch/providers").mock(
        return_value=httpx.Response(200, json=TMDB_WATCH_PROVIDERS_RESPONSE)
    )
    async with httpx.AsyncClient() as client:
        poster_url, platforms = await get_movie_details(client, "fake_key", 872585, "GB")
    assert poster_url == "https://image.tmdb.org/t/p/w300/oppenheimer.jpg"
    assert len(platforms) == 1
    assert platforms[0].provider_name == "Netflix"
    assert platforms[0].logo_path == "https://image.tmdb.org/t/p/w45/netflix.png"


@respx.mock
async def test_get_movie_details_no_providers_for_country():
    respx.get("https://api.themoviedb.org/3/movie/872585").mock(
        return_value=httpx.Response(200, json=TMDB_MOVIE_DETAILS_RESPONSE)
    )
    respx.get("https://api.themoviedb.org/3/movie/872585/watch/providers").mock(
        return_value=httpx.Response(200, json={"results": {}})
    )
    async with httpx.AsyncClient() as client:
        poster_url, platforms = await get_movie_details(client, "fake_key", 872585, "US")
    assert platforms == []


@respx.mock
async def test_enrich_films_sets_not_found_status():
    respx.get("https://api.themoviedb.org/3/search/movie").mock(
        return_value=httpx.Response(200, json=TMDB_EMPTY_SEARCH)
    )
    from scraper import ScrapedFilm
    results = await enrich_films("fake_key", "GB", [ScrapedFilm(slug="unknown-xyz", title="Unknown XYZ")])
    assert results["unknown-xyz"].tmdb_status == "not_found"


@respx.mock
async def test_enrich_films_found_film():
    respx.get("https://api.themoviedb.org/3/search/movie").mock(
        return_value=httpx.Response(200, json=TMDB_SEARCH_RESPONSE)
    )
    respx.get("https://api.themoviedb.org/3/movie/872585").mock(
        return_value=httpx.Response(200, json=TMDB_MOVIE_DETAILS_RESPONSE)
    )
    respx.get("https://api.themoviedb.org/3/movie/872585/watch/providers").mock(
        return_value=httpx.Response(200, json=TMDB_WATCH_PROVIDERS_RESPONSE)
    )
    from scraper import ScrapedFilm
    results = await enrich_films("fake_key", "GB", [ScrapedFilm(slug="oppenheimer-2023", title="Oppenheimer")])
    film = results["oppenheimer-2023"]
    assert film.tmdb_status == "found"
    assert film.tmdb_id == 872585
    assert film.poster_url == "https://image.tmdb.org/t/p/w300/oppenheimer.jpg"
    assert film.streaming_platforms[0].provider_name == "Netflix"
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_tmdb.py -v
```

Expected: `ModuleNotFoundError: No module named 'tmdb'`

**Step 3: Write minimal implementation**

Create `tmdb.py`:

```python
import asyncio
from datetime import datetime, timezone
from typing import Optional

import httpx

from models import Film, StreamingPlatform
from scraper import ScrapedFilm

TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p"

_semaphore = asyncio.Semaphore(10)


async def search_movie(
    client: httpx.AsyncClient, api_key: str, title: str
) -> Optional[int]:
    """Search TMDB by title. Returns tmdb_id of first result, or None."""
    async with _semaphore:
        response = await client.get(
            f"{TMDB_BASE}/search/movie",
            params={"api_key": api_key, "query": title},
        )
    response.raise_for_status()
    results = response.json().get("results", [])
    return results[0]["id"] if results else None


async def get_movie_details(
    client: httpx.AsyncClient, api_key: str, tmdb_id: int, country: str
) -> tuple[Optional[str], list[StreamingPlatform]]:
    """Fetch poster URL and flatrate streaming providers for a film."""
    async with _semaphore:
        movie_resp, providers_resp = await asyncio.gather(
            client.get(f"{TMDB_BASE}/movie/{tmdb_id}", params={"api_key": api_key}),
            client.get(
                f"{TMDB_BASE}/movie/{tmdb_id}/watch/providers",
                params={"api_key": api_key},
            ),
        )
    movie_resp.raise_for_status()
    providers_resp.raise_for_status()

    poster_path = movie_resp.json().get("poster_path")
    poster_url = f"{TMDB_IMAGE_BASE}/w300{poster_path}" if poster_path else None

    country_data = providers_resp.json().get("results", {}).get(country, {})
    flatrate = country_data.get("flatrate", [])
    platforms = [
        StreamingPlatform(
            provider_id=p["provider_id"],
            provider_name=p["provider_name"],
            logo_path=f"{TMDB_IMAGE_BASE}/w45{p['logo_path']}" if p.get("logo_path") else None,
        )
        for p in flatrate
    ]

    return poster_url, platforms


async def _enrich_one(
    client: httpx.AsyncClient, api_key: str, country: str, scraped: ScrapedFilm
) -> Film:
    """Enrich a single film. Returns Film with tmdb_status set."""
    now = datetime.now(timezone.utc).isoformat()

    tmdb_id = await search_movie(client, api_key, scraped.title)
    if tmdb_id is None:
        return Film(
            letterboxd_slug=scraped.slug,
            title=scraped.title,
            tmdb_status="not_found",
            country=country,
            last_checked=now,
        )

    try:
        poster_url, platforms = await get_movie_details(client, api_key, tmdb_id, country)
    except Exception:
        return Film(
            letterboxd_slug=scraped.slug,
            title=scraped.title,
            tmdb_id=tmdb_id,
            tmdb_status="error",
            country=country,
            last_checked=now,
        )

    return Film(
        letterboxd_slug=scraped.slug,
        title=scraped.title,
        tmdb_id=tmdb_id,
        tmdb_status="found",
        poster_url=poster_url,
        streaming_platforms=platforms,
        country=country,
        last_checked=now,
    )


async def enrich_films(
    api_key: str, country: str, scraped_films: list[ScrapedFilm]
) -> dict[str, Film]:
    """Enrich a list of scraped films concurrently. Returns dict slug → Film."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        tasks = [_enrich_one(client, api_key, country, f) for f in scraped_films]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    enriched: dict[str, Film] = {}
    for scraped, result in zip(scraped_films, results):
        if isinstance(result, Exception):
            enriched[scraped.slug] = Film(
                letterboxd_slug=scraped.slug,
                title=scraped.title,
                tmdb_status="error",
                country=country,
            )
        else:
            enriched[scraped.slug] = result

    return enriched
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_tmdb.py -v
```

Expected: 6 tests PASS.

**Step 5: Commit**

```bash
git add tmdb.py tests/test_tmdb.py
git commit -m "feat: add TMDB client with two-step enrichment and semaphore concurrency"
```

---

## Task 7: Scheduler and Refresh Orchestration

**Files:**
- Create: `scheduler.py`
- Create: `tests/test_scheduler.py`

The scheduler wires APScheduler to the refresh job. The `run_refresh()` coroutine is also called by the manual refresh endpoint in `main.py`.

**Step 1: Write the failing tests**

Create `tests/test_scheduler.py`:

```python
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch
from scraper import ScrapedFilm
from models import Film


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
    import database, scheduler
    await database.init_db(tmp_db)

    import asyncio

    async def slow_scrape(username):
        await asyncio.sleep(0.1)
        return []

    with patch("scheduler.scrape_watchlist", new=slow_scrape):
        with patch("scheduler.enrich_films", new=AsyncMock(return_value={})):
            result1, result2 = await asyncio.gather(
                scheduler.run_refresh("u", "k", "GB", tmp_db),
                scheduler.run_refresh("u", "k", "GB", tmp_db),
            )

    # One should have run, one should have been skipped
    assert (result1 is True) != (result2 is True)  # exactly one True, one False


def test_get_refresh_state_initial():
    import scheduler
    # Reset state for test isolation
    scheduler._refresh_state["is_refreshing"] = False
    assert scheduler.get_refresh_state() is False
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_scheduler.py -v
```

Expected: `ModuleNotFoundError: No module named 'scheduler'`

**Step 3: Write minimal implementation**

Create `scheduler.py`:

```python
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
_refresh_state: dict = {"is_refreshing": False}

_scheduler: Optional[AsyncIOScheduler] = None


async def run_refresh(
    username: str,
    tmdb_api_key: str,
    country: str,
    db_path: Path = database.DB_PATH,
) -> bool:
    """
    Run the full scrape → enrich → store pipeline.
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

        logger.info("Refresh complete.")
        return True
    finally:
        _refresh_state["is_refreshing"] = False


def get_refresh_state() -> bool:
    return _refresh_state["is_refreshing"]


def start_scheduler(username: str, tmdb_api_key: str, country: str, cron_expr: str) -> None:
    """Create and start the APScheduler with the refresh job."""
    global _scheduler

    # Parse cron expression (5 fields: min hour dom mon dow)
    parts = cron_expr.split()
    minute, hour, day, month, day_of_week = parts

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
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_scheduler.py -v
```

Expected: 3 tests PASS.

**Step 5: Commit**

```bash
git add scheduler.py tests/test_scheduler.py
git commit -m "feat: add scheduler with refresh orchestration and concurrent-run protection"
```

---

## Task 8: FastAPI App and Routes

**Files:**
- Create: `main.py`
- Create: `tests/test_routes.py`

Routes:
- `GET /` — render index.html with films and last_updated
- `POST /refresh` — trigger manual refresh, return JSON status
- `GET /health` — return `{"status": "ok"}` (used by Docker HEALTHCHECK)

**Step 1: Write the failing tests**

Create `tests/test_routes.py`:

```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock
from models import Film, StreamingPlatform


@pytest.fixture
def mock_settings():
    settings = MagicMock()
    settings.letterboxd_username = "testuser"
    settings.tmdb_api_key = "key"
    settings.country = "GB"
    settings.refresh_schedule = "0 0 * * 0"
    return settings


@pytest.fixture
def client(mock_settings):
    with patch("main.settings", mock_settings):
        from main import app
        return TestClient(app)


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_index_returns_200(client):
    films = [
        Film(
            letterboxd_slug="oppenheimer-2023",
            title="Oppenheimer",
            tmdb_status="found",
            poster_url="https://example.com/poster.jpg",
            streaming_platforms=[
                StreamingPlatform(provider_id=8, provider_name="Netflix")
            ],
        )
    ]
    with (
        patch("main.database.get_all_films", new=AsyncMock(return_value=films)),
        patch("main.database.get_last_updated", new=AsyncMock(return_value="2026-01-01T00:00:00")),
    ):
        response = client.get("/")
    assert response.status_code == 200
    assert "Oppenheimer" in response.text
    assert "Netflix" in response.text


def test_refresh_triggers_when_idle(client):
    with patch("main.scheduler.run_refresh", new=AsyncMock(return_value=True)):
        with patch("main.scheduler.get_refresh_state", return_value=False):
            response = client.post("/refresh")
    assert response.status_code == 200
    assert response.json()["status"] == "started"


def test_refresh_rejected_when_busy(client):
    with patch("main.scheduler.get_refresh_state", return_value=True):
        response = client.post("/refresh")
    assert response.status_code == 200
    assert response.json()["status"] == "already_running"
```

**Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_routes.py -v
```

Expected: `ModuleNotFoundError: No module named 'main'`

**Step 3: Write minimal implementation**

Create `main.py`:

```python
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request

import database
import scheduler
from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await database.init_db()
    scheduler.start_scheduler(
        username=settings.letterboxd_username,
        tmdb_api_key=settings.tmdb_api_key,
        country=settings.country,
        cron_expr=settings.refresh_schedule,
    )
    yield
    # Shutdown
    scheduler.stop_scheduler()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    films = await database.get_all_films()
    last_updated = await database.get_last_updated()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "films": films,
            "last_updated": last_updated,
            "is_refreshing": scheduler.get_refresh_state(),
        },
    )


@app.post("/refresh")
async def refresh(background_tasks: BackgroundTasks):
    if scheduler.get_refresh_state():
        return {"status": "already_running"}

    background_tasks.add_task(
        scheduler.run_refresh,
        settings.letterboxd_username,
        settings.tmdb_api_key,
        settings.country,
    )
    return {"status": "started"}
```

**Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_routes.py -v
```

Expected: 4 tests PASS.

**Step 5: Run full test suite to confirm nothing is broken**

```bash
uv run pytest -v
```

Expected: All tests PASS.

**Step 6: Commit**

```bash
git add main.py tests/test_routes.py
git commit -m "feat: add FastAPI app with index, refresh, and health routes"
```

---

## Task 9: HTML Template

**Files:**
- Create: `templates/index.html`

No unit tests — validated by running the app locally and visually checking.

**Step 1: Create the template**

Create `templates/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Watchlist</title>
  <link rel="stylesheet" href="/static/style.css" />
</head>
<body>
  <header>
    <h1>Watchlist</h1>
    <div class="meta">
      {% if last_updated %}
        Last updated: {{ last_updated }}
      {% else %}
        No data yet — trigger a refresh below.
      {% endif %}
    </div>
    <form method="post" action="/refresh">
      <button type="submit" {% if is_refreshing %}disabled{% endif %}>
        {% if is_refreshing %}Refreshing…{% else %}Refresh now{% endif %}
      </button>
    </form>
  </header>

  <main>
    {% if not films %}
      <p class="empty">No films found. Click "Refresh now" to fetch your watchlist.</p>
    {% else %}
      <ul class="film-grid">
        {% for film in films %}
        <li class="film-card">
          {% if film.poster_url %}
            <img src="{{ film.poster_url }}" alt="{{ film.title }}" loading="lazy" />
          {% else %}
            <div class="no-poster">No poster</div>
          {% endif %}
          <div class="film-info">
            <h2>{{ film.title }}{% if film.year %} <span class="year">({{ film.year }})</span>{% endif %}</h2>
            {% if film.streaming_platforms %}
              <ul class="platforms">
                {% for platform in film.streaming_platforms %}
                <li>
                  {% if platform.logo_path %}
                    <img src="{{ platform.logo_path }}" alt="{{ platform.provider_name }}" title="{{ platform.provider_name }}" />
                  {% else %}
                    {{ platform.provider_name }}
                  {% endif %}
                </li>
                {% endfor %}
              </ul>
            {% elif film.tmdb_status == "not_found" %}
              <p class="unavailable">Not found on TMDB</p>
            {% else %}
              <p class="unavailable">Not streaming in {{ film.country }}</p>
            {% endif %}
          </div>
        </li>
        {% endfor %}
      </ul>
    {% endif %}
  </main>
</body>
</html>
```

**Step 2: Verify by running the app**

```bash
uv run uvicorn main:app --reload --port 8000
```

Open `http://localhost:8000` — should render without errors (even with empty DB).

**Step 3: Commit**

```bash
git add templates/index.html
git commit -m "feat: add Jinja2 index template with film grid and refresh button"
```

---

## Task 10: Static CSS

**Files:**
- Create: `static/style.css`

**Step 1: Create basic stylesheet**

Create `static/style.css`:

```css
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: system-ui, sans-serif;
  background: #0f0f0f;
  color: #e0e0e0;
  min-height: 100vh;
  padding: 2rem;
}

header {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  margin-bottom: 2rem;
  flex-wrap: wrap;
}

header h1 { font-size: 1.5rem; font-weight: 600; }

.meta { color: #888; font-size: 0.85rem; }

button {
  padding: 0.4rem 1rem;
  background: #2a2a2a;
  color: #e0e0e0;
  border: 1px solid #444;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.85rem;
}

button:hover:not(:disabled) { background: #3a3a3a; }
button:disabled { opacity: 0.5; cursor: not-allowed; }

.film-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 1.5rem;
  list-style: none;
}

.film-card {
  background: #1a1a1a;
  border-radius: 6px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.film-card img[alt]:not([alt=""]) {
  width: 100%;
  aspect-ratio: 2/3;
  object-fit: cover;
  display: block;
}

.no-poster {
  width: 100%;
  aspect-ratio: 2/3;
  background: #2a2a2a;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #555;
  font-size: 0.75rem;
}

.film-info { padding: 0.75rem; flex: 1; }

.film-info h2 { font-size: 0.85rem; font-weight: 500; margin-bottom: 0.5rem; }
.year { color: #888; font-weight: 400; }

.platforms {
  list-style: none;
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
}

.platforms img { width: 28px; height: 28px; border-radius: 4px; }

.unavailable { color: #555; font-size: 0.75rem; }

.empty { color: #555; text-align: center; margin-top: 4rem; }
```

**Step 2: Commit**

```bash
git add static/style.css
git commit -m "feat: add dark theme CSS for film grid"
```

---

## Task 11: Docker

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`

**Step 1: Create Dockerfile**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

RUN mkdir -p data

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Note: uses `urllib.request` for healthcheck (no curl needed in slim image).

**Step 2: Create docker-compose.yml**

```yaml
services:
  app:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
      - ./.env:/app/.env:ro
    restart: unless-stopped
    environment:
      - PYTHONUNBUFFERED=1
```

**Step 3: Build and test**

```bash
# Must have a .env file first
cp .env.example .env
# Edit .env with real values, then:
docker compose up --build
```

Expected: container starts, `http://localhost:8000` responds, `http://localhost:8000/health` returns `{"status":"ok"}`.

**Step 4: Commit**

```bash
git add Dockerfile docker-compose.yml
git commit -m "feat: add Docker and docker-compose with health check and data volume"
```

---

## Task 12: README

**Files:**
- Create: `README.md`

**Step 1: Create README.md**

```markdown
# watchlist.db

Self-hosted web app that shows your Letterboxd watchlist alongside streaming availability for your country.

## Requirements

- Docker and Docker Compose
- A [TMDB API key](https://www.themoviedb.org/settings/api) (free)
- A public Letterboxd watchlist

## Setup

1. Clone the repo:
   ```bash
   git clone https://github.com/your-username/watchlist.db
   cd watchlist.db
   ```

2. Copy and edit the config:
   ```bash
   cp .env.example .env
   ```

   Edit `.env`:
   ```env
   LETTERBOXD_USERNAME=your_letterboxd_username
   TMDB_API_KEY=your_tmdb_api_key
   COUNTRY=GB          # ISO 3166-1 alpha-2 country code
   REFRESH_SCHEDULE=0 0 * * 0  # cron — default: weekly Sunday midnight
   ```

3. Start the app:
   ```bash
   docker compose up -d
   ```

4. Open [http://localhost:8000](http://localhost:8000)

5. Click **Refresh now** to fetch your watchlist for the first time.

## Notes

- Your watchlist must be set to **public** on Letterboxd.
- Data is cached in `./data/watchlist.db` (SQLite). This persists across restarts via Docker volume.
- Streaming data comes from TMDB's watch provider data. Not all films will have matches.
- Only **subscription** (flatrate) streaming services are shown — not rent/buy.

## Development

```bash
# Install dependencies
uv sync --group dev

# Run locally
cp .env.example .env  # edit with real values
uv run uvicorn main:app --reload

# Run tests
uv run pytest -v
```

## Country Codes

Use ISO 3166-1 alpha-2 codes: `US`, `GB`, `AU`, `CA`, `DE`, `FR`, etc.
```

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add README with setup and development instructions"
```

---

## Final: End-to-End Smoke Test

**Step 1: Run full test suite**

```bash
uv run pytest -v
```

Expected: All tests PASS. Count should be approximately 20+.

**Step 2: Run the app locally and trigger a refresh**

Requires a real `.env` with valid credentials.

```bash
uv run uvicorn main:app --reload --port 8000
```

1. Open `http://localhost:8000`
2. Click **Refresh now**
3. Wait for refresh to complete (check terminal logs)
4. Reload page — films should appear with streaming providers

**Step 3: Test Docker end-to-end**

```bash
docker compose up --build
```

Wait for health check to pass, then repeat step 2.

---

## Completion Checklist

- [ ] All tests pass (`uv run pytest -v`)
- [ ] App starts without errors locally
- [ ] Letterboxd scraper follows pagination
- [ ] TMDB enrichment runs concurrently with semaphore
- [ ] Films with no TMDB match show `not_found` gracefully in UI
- [ ] Manual refresh button works and shows "Refreshing…" state
- [ ] "Last updated" timestamp appears on page
- [ ] Docker container starts and health check passes
- [ ] `./data/watchlist.db` persists across container restarts
- [ ] `.env.example` is committed, `.env` is gitignored
