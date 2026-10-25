"""Worker settings (kept separate from the API's settings object)."""

from functools import lru_cache
from typing import Literal

from app.core.database_url import normalize_database_url
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    environment: Literal["local", "test", "staging", "production"] = "local"
    log_level: str = "INFO"

    redis_url: str = "redis://localhost:6379/0"
    database_url: str = "postgresql+psycopg://codepilot:codepilot@localhost:5432/codepilot"

    @field_validator("database_url", mode="after")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        return normalize_database_url(value)

    # Periodic Codeforces sync cadence (wired to Celery beat in Phase 1).
    cf_sync_interval_minutes: int = 30


@lru_cache
def get_settings() -> WorkerSettings:
    return WorkerSettings()
