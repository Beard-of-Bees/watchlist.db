import asyncio
from datetime import datetime, timezone
from typing import Optional

import httpx

from models import Film, StreamingPlatform
from scraper import ScrapedFilm

TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p"

_semaphore = asyncio.Semaphore(10)


async def search_movie(client: httpx.AsyncClient, api_key: str, title: str) -> Optional[int]:
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
) -> tuple[Optional[str], Optional[int], list[str], list[StreamingPlatform], Optional[str]]:
    """Fetch poster URL, year, genres, flatrate streaming providers, and watch link for a film."""
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

    movie_data = movie_resp.json()
    poster_path = movie_data.get("poster_path")
    poster_url = f"{TMDB_IMAGE_BASE}/w300{poster_path}" if poster_path else None

    release_date = movie_data.get("release_date") or ""
    year = int(release_date[:4]) if release_date and len(release_date) >= 4 and release_date[:4].isdigit() else None

    genres = [g["name"] for g in movie_data.get("genres", [])]

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
    watch_link = country_data.get("link")
    return poster_url, year, genres, platforms, watch_link


async def _enrich_one(
    client: httpx.AsyncClient, api_key: str, country: str, scraped: ScrapedFilm
) -> Film:
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
        poster_url, year, genres, platforms, watch_link = await get_movie_details(client, api_key, tmdb_id, country)
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
        year=year,
        tmdb_id=tmdb_id,
        tmdb_status="found",
        poster_url=poster_url,
        genres=genres,
        streaming_platforms=platforms,
        watch_link=watch_link,
        country=country,
        last_checked=now,
    )


async def enrich_films(api_key: str, country: str, scraped_films: list[ScrapedFilm]) -> dict[str, Film]:
    """Enrich a list of scraped films concurrently. Returns dict slug -> Film."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        tasks = [_enrich_one(client, api_key, country, film) for film in scraped_films]
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
