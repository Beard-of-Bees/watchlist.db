import pytest
from pydantic import ValidationError


def test_valid_config(monkeypatch):
    monkeypatch.setenv("LETTERBOXD_USERNAME", "testuser")
    monkeypatch.setenv("TMDB_API_KEY", "abc123")
    monkeypatch.delenv("COUNTRY", raising=False)
    monkeypatch.delenv("REFRESH_SCHEDULE", raising=False)

    from importlib import reload
    import config

    reload(config)

    assert config.settings.letterboxd_username == "testuser"
    assert config.settings.tmdb_api_key == "abc123"
    assert config.settings.country == "GB"
    assert config.settings.refresh_schedule == "0 0 * * 0"


def test_missing_required_vars(monkeypatch):
    monkeypatch.delenv("LETTERBOXD_USERNAME", raising=False)
    monkeypatch.delenv("TMDB_API_KEY", raising=False)

    from importlib import reload
    import config

    with pytest.raises((ValidationError, Exception)):
        from config import Settings

        Settings(_env_file=None)
