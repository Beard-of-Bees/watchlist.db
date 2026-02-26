import httpx
import respx

from scraper import _parse_watchlist_page, scrape_watchlist

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

MODERN_WATCHLIST_HTML = """
<html><body>
<div class="poster-grid">
  <ul class="grid -p125 -scaled128">
    <li class="griditem">
      <div class="react-component"
           data-component-class="LazyPoster"
           data-item-slug="kung-fu-hustle"
           data-target-link="/film/kung-fu-hustle/">
        <div class="poster film-poster">
          <img class="image" alt="Kung Fu Hustle" />
        </div>
      </div>
    </li>
    <li class="griditem">
      <div class="react-component"
           data-component-class="LazyPoster"
           data-item-slug="genius-2016"
           data-target-link="/film/genius-2016/">
        <div class="poster film-poster">
          <img class="image" alt="Genius" />
        </div>
      </div>
    </li>
  </ul>
</div>
<div class="pagination">
  <div class="paginate-nextprev"><a class="next" href="/testuser/watchlist/page/2/">Older</a></div>
</div>
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


def test_parse_modern_lazy_poster_markup():
    films, has_next = _parse_watchlist_page(MODERN_WATCHLIST_HTML)
    assert len(films) == 2
    assert films[0].slug == "kung-fu-hustle"
    assert films[0].title == "Kung Fu Hustle"
    assert films[1].slug == "genius-2016"
    assert has_next is True


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
