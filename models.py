from typing import Optional

from pydantic import BaseModel, Field


class StreamingPlatform(BaseModel):
    provider_id: int
    provider_name: str
    logo_path: Optional[str] = None


class Film(BaseModel):
    id: Optional[int] = None
    letterboxd_slug: str
    title: str
    year: Optional[int] = None
    tmdb_id: Optional[int] = None
    tmdb_status: str = "pending"  # pending | found | not_found | error
    poster_url: Optional[str] = None
    overview: Optional[str] = None
    runtime_minutes: Optional[int] = None
    original_language: Optional[str] = None
    genres: list[str] = Field(default_factory=list)
    streaming_platforms: list[StreamingPlatform] = Field(default_factory=list)
    watch_link: Optional[str] = None
    country: Optional[str] = None
    last_checked: Optional[str] = None  # ISO timestamp string
    source: str = "letterboxd"
