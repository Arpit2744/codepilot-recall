"""Database URL normalization tests (Phase 6, Neon compatibility)."""

import pytest

from app.core.database_url import normalize_database_url


def test_neon_postgresql_url_becomes_driver_qualified_with_sslmode():
    raw = "postgresql://user:pass@ep-cool-name-pooler.eu-central-1.aws.neon.tech/neondb"
    assert normalize_database_url(raw) == (
        "postgresql+psycopg://user:pass@"
        "ep-cool-name-pooler.eu-central-1.aws.neon.tech/neondb?sslmode=require"
    )


def test_neon_url_with_existing_params_keeps_them_and_joins_sslmode():
    raw = (
        "postgresql://user:pass@ep-x-pooler.region.aws.neon.tech/neondb"
        "?options=project%3Dep-x"
    )
    normalized = normalize_database_url(raw)
    assert normalized == (
        "postgresql+psycopg://user:pass@ep-x-pooler.region.aws.neon.tech/neondb"
        "?options=project%3Dep-x&sslmode=require"
    )


def test_existing_sslmode_is_never_duplicated():
    raw = "postgresql://u:p@ep-x.neon.tech/db?sslmode=verify-full"
    normalized = normalize_database_url(raw)
    assert normalized == "postgresql+psycopg://u:p@ep-x.neon.tech/db?sslmode=verify-full"
    assert normalized.count("sslmode") == 1


def test_driver_qualified_neon_url_gets_sslmode_scheme_unchanged():
    raw = "postgresql+psycopg://u:p@ep-x.neon.tech/db"
    assert normalize_database_url(raw) == (
        "postgresql+psycopg://u:p@ep-x.neon.tech/db?sslmode=require"
    )


def test_legacy_postgres_scheme_normalized():
    raw = "postgres://u:p@ep-x.neon.tech/db"
    assert normalize_database_url(raw) == (
        "postgresql+psycopg://u:p@ep-x.neon.tech/db?sslmode=require"
    )


def test_non_neon_host_left_without_sslmode():
    raw = "postgresql://codepilot:codepilot@localhost:5432/codepilot"
    assert normalize_database_url(raw) == (
        "postgresql+psycopg://codepilot:codepilot@localhost:5432/codepilot"
    )


def test_encoded_credentials_preserved_verbatim():
    raw = "postgresql://u:p%40ss%3Aword@ep-x.neon.tech/db"
    normalized = normalize_database_url(raw)
    assert "u:p%40ss%3Aword@" in normalized  # netloc rebuilt nowhere


def test_non_postgres_urls_untouched():
    assert normalize_database_url("sqlite+pysqlite:///./local.db") == (
        "sqlite+pysqlite:///./local.db"
    )
    assert normalize_database_url("") == ""
    assert normalize_database_url(None) is None


def test_settings_validator_normalizes_database_url(monkeypatch):
    """API startup, Alembic (via settings), and Actions all read this field."""
    from app.core.config import Settings

    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://u:p@ep-y-pooler.region.aws.neon.tech/db?options=project%3Dep-y",
    )
    normalized = Settings().database_url
    assert normalized.startswith("postgresql+psycopg://")
    assert normalized.endswith("&sslmode=require") or "sslmode=require" in normalized


@pytest.mark.parametrize(
    "raw",
    [
        "postgresql://u:p@ep-z.neon.tech/db?a=1&sslmode=require&b=2",
    ],
)
def test_sslmode_position_is_preserved_when_present(raw):
    assert normalize_database_url(raw) == (
        "postgresql+psycopg://u:p@ep-z.neon.tech/db?a=1&sslmode=require&b=2"
    )
