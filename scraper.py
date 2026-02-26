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

    films: list[ScrapedFilm] = []
    seen_slugs: set[str] = set()

    # Legacy Letterboxd markup.
    for poster in soup.select("li.poster-container div.film-poster"):
        slug = (poster.get("data-film-slug") or "").strip()
        if not slug or slug in seen_slugs:
            continue
        img = poster.find("img")
        title = img["alt"] if img and img.get("alt") else slug
        films.append(ScrapedFilm(slug=slug, title=title))
        seen_slugs.add(slug)

    # Current Letterboxd watchlist markup uses a React wrapper with data-item-slug.
    for card in soup.select("div.react-component[data-component-class='LazyPoster']"):
        slug = (card.get("data-item-slug") or "").strip()
        if not slug:
            target_link = (card.get("data-target-link") or "").strip("/")
            # Expected format: film/<slug>
            parts = target_link.split("/")
            if len(parts) >= 2 and parts[0] == "film":
                slug = parts[1].strip()
        if not slug or slug in seen_slugs:
            continue

        img = card.find("img")
        title = img["alt"] if img and img.get("alt") else (card.get("data-item-name") or slug)
        films.append(ScrapedFilm(slug=slug, title=title))
        seen_slugs.add(slug)

    has_next = soup.select_one("a.next") is not None
    return films, has_next
