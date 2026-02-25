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
   REFRESH_SCHEDULE=0 0 * * 0  # cron - default: weekly Sunday midnight
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
- Only **subscription** (flatrate) streaming services are shown - not rent/buy.

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
