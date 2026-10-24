"""Configuration parsing tests — regression cover for the CORS env parsing bug.

Pydantic Settings JSON-decodes complex fields before validators run; plain
`CORS_ORIGINS=http://localhost:3000` therefore raised SettingsError inside
containers until the field was annotated with NoDecode.
"""

import pytest

from app.core.config import Settings, get_settings


@pytest.fixture(autouse=True)
def _fresh_settings_cache():
    """Isolate each case from the lru_cache and clear any env override."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_single_origin_env_string_parses_to_list(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000")
    assert Settings().cors_origins == ["http://localhost:3000"]


def test_comma_separated_origins_parse_to_list(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000,https://example.com")
    assert Settings().cors_origins == ["http://localhost:3000", "https://example.com"]


def test_default_origins_without_env_override(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    assert Settings().cors_origins == ["http://localhost:3000"]


def test_cached_get_settings_reflects_env(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example,https://b.example")
    assert get_settings().cors_origins == ["https://a.example", "https://b.example"]
