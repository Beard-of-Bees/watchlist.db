from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    letterboxd_username: str
    tmdb_api_key: str
    country: str = "GB"
    refresh_schedule: str = "0 0 * * 0"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = Settings()
