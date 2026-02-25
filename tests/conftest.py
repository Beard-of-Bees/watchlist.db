from pathlib import Path

import pytest


@pytest.fixture
def tmp_db(tmp_path) -> Path:
    """Returns path to a temporary SQLite database file."""
    return tmp_path / "test.db"
