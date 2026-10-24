"""Application settings loaded from environment variables (12-factor style)."""

from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "CodePilot Recall"
    api_version: str = "0.1.0"
    environment: Literal["local", "test", "staging", "production"] = "local"
    log_level: str = "INFO"

    api_v1_prefix: str = "/api/v1"

    database_url: str = "postgresql+psycopg://codepilot:codepilot@localhost:5432/codepilot"
    redis_url: str = "redis://localhost:6379/0"

    cors_origins: list[str] = ["http://localhost:3000"]

    # Codeforces integration knobs (used from Phase 1 onwards).
    cf_api_base_url: str = "https://codeforces.com/api"
    cf_request_interval_seconds: float = 2.5
    cf_sync_interval_minutes: int = 30

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_csv_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def _upper_log_level(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor; tests override env vars before first import."""
    return Settings()
