import httpx
import respx

from tmdb import enrich_films, get_movie_details, search_movie

TMDB_SEARCH_RESPONSE = {
    "results": [{"id": 872585, "title": "Oppenheimer", "release_date": "2023-07-21"}]
}

TMDB_WATCH_PROVIDERS_RESPONSE = {
    "results": {
        "GB": {
            "link": "https://www.themoviedb.org/movie/872585/watch?locale=GB",
            "flatrate": [
                {
                    "provider_id": 8,
                    "provider_name": "Netflix",
                    "logo_path": "/netflix.png",
                }
            ],
        }
    }
}

TMDB_MOVIE_DETAILS_RESPONSE = {
    "id": 872585,
    "title": "Oppenheimer",
    "release_date": "2023-07-21",
    "poster_path": "/oppenheimer.jpg",
    "genres": [{"id": 18, "name": "Drama"}, {"id": 36, "name": "History"}],
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
        poster_url, year, genres, platforms, watch_link = await get_movie_details(client, "fake_key", 872585, "GB")
    assert poster_url == "https://image.tmdb.org/t/p/w300/oppenheimer.jpg"
    assert year == 2023
    assert genres == ["Drama", "History"]
    assert len(platforms) == 1
    assert platforms[0].provider_name == "Netflix"
    assert platforms[0].logo_path == "https://image.tmdb.org/t/p/w45/netflix.png"
    assert watch_link == "https://www.themoviedb.org/movie/872585/watch?locale=GB"


@respx.mock
async def test_get_movie_details_no_providers_for_country():
    respx.get("https://api.themoviedb.org/3/movie/872585").mock(
        return_value=httpx.Response(200, json=TMDB_MOVIE_DETAILS_RESPONSE)
    )
    respx.get("https://api.themoviedb.org/3/movie/872585/watch/providers").mock(
        return_value=httpx.Response(200, json={"results": {}})
    )
    async with httpx.AsyncClient() as client:
        poster_url, year, genres, platforms, watch_link = await get_movie_details(client, "fake_key", 872585, "US")
    assert poster_url == "https://image.tmdb.org/t/p/w300/oppenheimer.jpg"
    assert year == 2023
    assert genres == ["Drama", "History"]
    assert platforms == []
    assert watch_link is None


@respx.mock
async def test_enrich_films_sets_not_found_status():
    respx.get("https://api.themoviedb.org/3/search/movie").mock(
        return_value=httpx.Response(200, json=TMDB_EMPTY_SEARCH)
    )
    from scraper import ScrapedFilm

    results = await enrich_films(
        "fake_key", "GB", [ScrapedFilm(slug="unknown-xyz", title="Unknown XYZ")]
    )
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

    results = await enrich_films(
        "fake_key", "GB", [ScrapedFilm(slug="oppenheimer-2023", title="Oppenheimer")]
    )
    film = results["oppenheimer-2023"]
    assert film.tmdb_status == "found"
    assert film.tmdb_id == 872585
    assert film.year == 2023
    assert film.poster_url == "https://image.tmdb.org/t/p/w300/oppenheimer.jpg"
    assert film.streaming_platforms[0].provider_name == "Netflix"
