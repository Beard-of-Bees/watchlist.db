# Letterboxd Streaming Tracker — Project Brief

## Overview

A self-hosted Python web app that scrapes a Letterboxd watchlist, enriches each film with streaming availability data from the TMDB API, and displays results on a simple web page. Data is cached locally so the page loads instantly — scraping and enrichment runs on a schedule in the background.

This is intended as an open source project for self-hosting. Users bring their own TMDB API key and run it via Docker.

---

## Architecture

**On-demand is not viable** — scraping + N TMDB API calls will take too long for a page load. Instead:

- A background scheduler scrapes and enriches data periodically, storing results in SQLite
- The web page reads from the database and renders instantly
- A manual "refresh now" trigger should also be available via the UI

```
Scheduler (APScheduler)
    → Scrape Letterboxd HTML (httpx + BeautifulSoup)
    → Enrich with TMDB API calls (async httpx, concurrent)
    → Store results in SQLite

FastAPI
    → Serve cached results from SQLite
    → Jinja2 template for the web page
    → Endpoint to trigger manual refresh
```

---

## Stack

| Concern | Library |
|---|---|
| Web framework | FastAPI |
| Templating | Jinja2 |
| HTTP client | httpx (async) |
| HTML parsing | BeautifulSoup4 |
| Database | SQLite via sqlite3 or SQLModel |
| Scheduling | APScheduler |
| Server | Uvicorn |

---

## Data Model

A single `films` table is sufficient to start:

```
id
letterboxd_slug
title
year
tmdb_id
poster_url
streaming_platforms (JSON array)
country
last_checked (timestamp)
source (letterboxd | manual)
```

---

## Configuration

Users configure via a `.env` file. Ship a `.env.example` in the repo.

```env
LETTERBOXD_USERNAME=your_username
TMDB_API_KEY=your_key_here
COUNTRY=GB
REFRESH_SCHEDULE=0 0 * * 0   # cron syntax, default weekly
```

The app should validate these on startup and fail loudly with a helpful message if any are missing.

---

## Scraping Notes

- Letterboxd has no public API — this scrapes HTML
- A public watchlist requires no auth; a private one needs session cookies (out of scope for v1 — require users to set their list to public)
- Letterboxd HTML structure may change — scraping logic should be isolated in its own module so it's easy to fix when it breaks
- Be respectful: don't hammer the site, add a delay between requests

---

## TMDB Integration

- Free API key, users register at themoviedb.org
- Use the `/movie/{id}/watch/providers` endpoint for streaming availability
- Filter by user's configured country
- Run enrichment calls concurrently with `asyncio.gather()` — don't do them sequentially or a large watchlist will take forever

---

## Docker Setup

### Dockerfile
```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### docker-compose.yml
```yaml
services:
  app:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
      - ./.env:/app/.env
    restart: unless-stopped
```

The `./data` volume mount persists the SQLite database across container restarts. Without it, cached data is lost on every restart.

---

## Project Structure

```
/
├── main.py                  # FastAPI app, routes
├── scraper.py               # Letterboxd scraping logic
├── tmdb.py                  # TMDB API calls
├── scheduler.py             # APScheduler setup
├── database.py              # SQLite read/write
├── templates/
│   └── index.html           # Jinja2 template
├── static/                  # CSS, any assets
├── data/                    # SQLite DB lives here (gitignored)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── README.md
```

---

## v1 Scope

- [ ] Scrape public Letterboxd watchlist by username
- [ ] Enrich each film with TMDB streaming providers for configured country
- [ ] Store results in SQLite
- [ ] Serve a simple web page showing films + where to stream them
- [ ] Background refresh on configured schedule
- [ ] Manual refresh trigger in UI
- [ ] "Last updated" timestamp displayed on page
- [ ] Docker Compose setup
- [ ] `.env.example` and clear README install instructions

## Out of Scope for v1

- Private watchlist support (requires auth cookie handling)
- Manual film list / sync with Letterboxd
- Hosted version
- Multiple watchlists
