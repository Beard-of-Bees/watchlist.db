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
