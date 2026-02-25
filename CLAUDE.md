# watchlist.db

Self-hosted Python web app that scrapes a Letterboxd watchlist, enriches each film with streaming availability from TMDB, and serves results from a SQLite cache. Background scheduler handles data refresh; the UI reads from cache and loads instantly.

## Project Purpose

- Open source, self-hosted, Docker Compose deployment
- Users bring their own TMDB API key and a public Letterboxd username
- v1: public watchlists only (no auth)

---

## Tech Stack

| Concern       | Library                            |
|---------------|------------------------------------|
| Web framework | FastAPI                            |
| Templating    | Jinja2                             |
| HTTP client   | httpx (async)                      |
| HTML parsing  | BeautifulSoup4                     |
| Database      | SQLite via aiosqlite               |
| Scheduling    | APScheduler (pin to 3.x)           |
| Config        | pydantic-settings                  |
| Server        | Uvicorn                            |
| Packaging     | uv + pyproject.toml                |

---

## Project Structure

```
/
├── main.py          # FastAPI app, routes, lifespan context manager
├── scraper.py       # Letterboxd scraping — ALL scraping logic here only
├── tmdb.py          # TMDB search + watch provider calls
├── scheduler.py     # APScheduler setup, wired into FastAPI lifespan
├── database.py      # SQLite read/write via aiosqlite
├── config.py        # pydantic-settings config, validated on startup
├── models.py        # Pydantic models for Film and related shapes
├── templates/
│   └── index.html   # Jinja2 template
├── static/          # CSS, assets
├── data/            # SQLite DB file (gitignored, persisted via Docker volume)
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── .env.example
└── README.md
```

---

## Key Architecture

### Scheduling
- APScheduler runs inside FastAPI's lifespan context manager (not as a separate process)
- Use `asyncio.Lock` to prevent concurrent refresh runs (scheduled + manual can collide)
- Track `is_refreshing: bool` state and expose it to the UI

### TMDB Enrichment — Two-Step Flow
Enrichment is NOT just one API call. The flow is:
1. **Search** → `GET /search/movie?query={title}&year={year}` → returns `tmdb_id`
2. **Providers** → `GET /movie/{tmdb_id}/watch/providers` → filter by `COUNTRY`

Not every Letterboxd film will match on TMDB. Track this with a `tmdb_status` field (values: `pending`, `found`, `not_found`, `error`).

Use `asyncio.Semaphore(10)` around concurrent TMDB calls — `asyncio.gather()` alone with a large watchlist will hit rate limits.

### Letterboxd Scraping
- Watchlists paginate at 28 films per page — scraper must loop until no next page
- Add a delay between page requests (1–2 seconds) — be a good citizen
- **All scraping logic lives in `scraper.py` only** — Letterboxd HTML structure changes; isolation means one file to fix
- No auth in v1 — require users to set their Letterboxd list to public

### Manual Refresh Endpoint
- Return `{"status": "already_running"}` if refresh is in progress — don't queue duplicates
- Surface refresh state in the UI ("Refreshing..." / "Last updated: X")

---

## Data Model

Single `films` table:

```sql
CREATE TABLE films (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    letterboxd_slug     TEXT UNIQUE NOT NULL,
    title               TEXT NOT NULL,
    year                INTEGER,
    tmdb_id             INTEGER,
    tmdb_status         TEXT DEFAULT 'pending',  -- pending|found|not_found|error
    poster_url          TEXT,
    streaming_platforms TEXT,                    -- JSON array, deserialize on read
    country             TEXT,
    last_checked        TEXT,                    -- ISO timestamp
    source              TEXT DEFAULT 'letterboxd'
);
```

---

## Configuration

Validated on startup via `pydantic-settings`. App must fail loudly with a clear message if required vars are missing — do not silently fall back to defaults.

```env
LETTERBOXD_USERNAME=your_username
TMDB_API_KEY=your_key_here
COUNTRY=GB
REFRESH_SCHEDULE=0 0 * * 0   # cron syntax, default: weekly Sunday midnight
```

Config lives in `config.py` as a `Settings(BaseSettings)` class. Import a single `settings` singleton everywhere.

---

## Development

```bash
# Install uv first: https://docs.astral.sh/uv/getting-started/installation/
uv sync
uv run uvicorn main:app --reload --port 8000
```

```bash
# Docker
docker compose up --build
```

Create a `.env` file based on `.env.example` before running.

---

## Common Pitfalls

- **Event loop blocking**: Use `aiosqlite` for all DB access. Never call bare `sqlite3` from async routes — it blocks the event loop.
- **Letterboxd pagination**: Scraper must follow paginated pages, not just scrape page 1.
- **APScheduler version**: Pin to `3.x` in `pyproject.toml`. v3 and v4 have incompatible APIs.
- **TMDB not_found**: Films added to Letterboxd under alternate titles or very obscure films may not match. Store `tmdb_status` so the UI can handle this gracefully rather than showing broken cards.
- **streaming_platforms is JSON**: Stored as a JSON string in SQLite. Always serialize on write, deserialize on read — don't let raw JSON strings leak into templates.
- **Semaphore on gather**: `asyncio.gather()` without a semaphore fires all requests simultaneously. Cap with `asyncio.Semaphore(10)`.

---

## SQLite Notes

- DB file: `data/watchlist.db` (mounted as Docker volume — without this, data is lost on container restart)
- Schema changes in v1: drop and recreate the table manually (no migration tooling needed yet)
- All DB interactions go through `database.py` — don't write SQL in routes or other modules

---

## Docker

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY . .
HEALTHCHECK --interval=30s --timeout=5s CMD curl -f http://localhost:8000/health || exit 1
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

The `docker-compose.yml` volume mount `./data:/app/data` is required to persist the SQLite DB.

---

## v1 Scope

- [ ] Scrape public Letterboxd watchlist by username (handle pagination)
- [ ] Enrich each film: TMDB search → TMDB watch providers for configured country
- [ ] Store results in SQLite with `tmdb_status` tracking
- [ ] Serve web page showing films + streaming availability
- [ ] Background refresh on configured cron schedule
- [ ] Manual refresh trigger in UI with status feedback
- [ ] "Last updated" timestamp on page
- [ ] Docker Compose setup with data volume
- [ ] `.env.example` and README install instructions

## Out of Scope (v1)

- Private watchlist support
- Multiple watchlists
- Hosted/cloud version
- Manual film management
