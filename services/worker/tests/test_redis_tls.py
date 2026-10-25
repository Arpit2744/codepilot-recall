"""TLS configuration for Redis URLs (Phase 6, Upstash rediss://)."""

import ssl

from app.core.redis_tls import redis_ssl_options


def test_rediss_url_requires_certificate_verification():
    options = redis_ssl_options("rediss://default:secret@host.upstash.io:6379")
    assert options == {"ssl_cert_reqs": ssl.CERT_REQUIRED}


def test_plain_redis_url_has_no_ssl_options():
    assert redis_ssl_options("redis://localhost:6379/0") is None
    assert redis_ssl_options(None) is None
    assert redis_ssl_options("") is None


def test_celery_app_applies_tls_for_rediss(monkeypatch):
    """The worker's Celery instance must configure broker/backend SSL for
    TLS-only endpoints, and leave plain redis:// untouched."""
    import importlib

    import worker.celery_app as celery_module
    from worker.config import get_settings

    monkeypatch.setenv("REDIS_URL", "rediss://default:secret@host.upstash.io:6379")
    get_settings.cache_clear()
    reloaded = importlib.reload(celery_module)
    try:
        conf = reloaded.celery_app.conf
        assert conf.broker_use_ssl == {"ssl_cert_reqs": ssl.CERT_REQUIRED}
        assert conf.redis_backend_use_ssl == {"ssl_cert_reqs": ssl.CERT_REQUIRED}
    finally:
        monkeypatch.delenv("REDIS_URL")
        get_settings.cache_clear()
        importlib.reload(celery_module)


def test_celery_app_plain_redis_has_no_ssl(monkeypatch):
    import importlib

    import worker.celery_app as celery_module
    from worker.config import get_settings

    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    get_settings.cache_clear()
    reloaded = importlib.reload(celery_module)
    try:
        conf = reloaded.celery_app.conf
        # Celery's unset default is False (no TLS), not None.
        assert not conf.get("broker_use_ssl")
        assert not conf.get("redis_backend_use_ssl")
    finally:
        monkeypatch.delenv("REDIS_URL")
        get_settings.cache_clear()
        importlib.reload(celery_module)
