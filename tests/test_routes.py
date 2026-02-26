from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

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
            streaming_platforms=[StreamingPlatform(provider_id=8, provider_name="Netflix")],
        )
    ]
    with (
        patch("main.database.get_all_films", new=AsyncMock(return_value=films)),
        patch(
            "main.database.get_last_updated",
            new=AsyncMock(return_value="2026-01-01T00:00:00"),
        ),
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


def test_get_all_platforms_deduplicates_and_sorts():
    from main import _get_all_platforms
    films = [
        Film(
            letterboxd_slug="a",
            title="A",
            streaming_platforms=[
                StreamingPlatform(provider_id=8, provider_name="Netflix"),
                StreamingPlatform(provider_id=337, provider_name="Disney+"),
            ],
        ),
        Film(
            letterboxd_slug="b",
            title="B",
            streaming_platforms=[
                StreamingPlatform(provider_id=8, provider_name="Netflix"),
                StreamingPlatform(provider_id=2100, provider_name="Apple TV+"),
            ],
        ),
    ]
    result = _get_all_platforms(films)
    assert len(result) == 3
    assert [p.provider_name for p in result] == ["Apple TV+", "Disney+", "Netflix"]


def test_get_all_platforms_empty():
    from main import _get_all_platforms
    assert _get_all_platforms([]) == []


def test_index_passes_all_platforms_to_template(client):
    films = [
        Film(
            letterboxd_slug="oppenheimer-2023",
            title="Oppenheimer",
            tmdb_status="found",
            streaming_platforms=[StreamingPlatform(provider_id=8, provider_name="Netflix")],
        )
    ]
    with (
        patch("main.database.get_all_films", new=AsyncMock(return_value=films)),
        patch("main.database.get_last_updated", new=AsyncMock(return_value=None)),
    ):
        response = client.get("/")
    assert response.status_code == 200
    assert 'data-provider-id="8"' in response.text
    assert 'data-platform-ids="8"' in response.text


def test_index_renders_film_popup_hooks_and_shell(client):
    films = [
        Film(
            letterboxd_slug="oppenheimer-2023",
            title="Oppenheimer",
            year=2023,
            tmdb_status="found",
            genres=["Drama", "History"],
            overview="The story of J. Robert Oppenheimer.",
            runtime_minutes=180,
            original_language="en",
            watch_link="https://www.themoviedb.org/movie/872585",
            streaming_platforms=[
                StreamingPlatform(provider_id=8, provider_name="Netflix"),
                StreamingPlatform(provider_id=9, provider_name="Prime Video"),
            ],
        )
    ]
    with (
        patch("main.database.get_all_films", new=AsyncMock(return_value=films)),
        patch("main.database.get_last_updated", new=AsyncMock(return_value=None)),
    ):
        response = client.get("/")

    assert response.status_code == 200
    assert 'data-film-popup-trigger="true"' in response.text
    assert 'data-overview="The story of J. Robert Oppenheimer.' in response.text
    assert 'data-runtime-minutes="180"' in response.text
    assert 'data-original-language="en"' in response.text
    assert 'id="film-dialog"' in response.text
    assert 'id="film-dialog-title"' in response.text
    assert 'id="film-dialog-services-active"' in response.text
    assert 'id="film-dialog-services-other"' in response.text
    assert 'id="film-dialog-synopsis"' in response.text
    assert 'id="film-dialog-tmdb-link"' in response.text
