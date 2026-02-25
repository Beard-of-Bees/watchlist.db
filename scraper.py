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
