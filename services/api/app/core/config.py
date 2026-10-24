"""Application settings loaded from environment variables (12-factor style)."""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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

    # NoDecode: pass the raw comma-separated env string to the validator
    # instead of letting pydantic-settings JSON-decode it first (which
    # crashes on plain "http://localhost:3000" values).
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    # Codeforces integration knobs (used from Phase 1 onwards).
    cf_api_base_url: str = "https://codeforces.com/api"
    cf_request_interval_seconds: float = 2.5
    cf_sync_interval_minutes: int = 30
    # Codeforces publishes ~1 request / 2 seconds as the polite upper bound;
    # the default interval stays above it on purpose.
    cf_status_page_size: int = 1000
    cf_max_retries: int = 5
    cf_backoff_base_seconds: float = 1.0
    cf_backoff_max_seconds: float = 60.0
    cf_connect_timeout_seconds: float = 5.0
    cf_read_timeout_seconds: float = 30.0
    cf_historical_max_pages: int = 200
    cf_incremental_max_pages: int = 20

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
