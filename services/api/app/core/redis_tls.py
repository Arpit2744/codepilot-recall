"""TLS handling for Redis URLs (Phase 6).

Upstash (and other managed Redis providers) expose TLS-only endpoints via
the ``rediss://`` scheme. Celery's Redis transport requires the SSL options
to be provided explicitly through ``broker_use_ssl`` /
``redis_backend_use_ssl``; a plain ``rediss://`` broker URL is not enough.
Local development keeps plain ``redis://`` with no SSL configuration.
"""

import ssl


def redis_ssl_options(redis_url: str | None) -> dict | None:
    """SSL options for Celery broker/backend when the URL requires TLS.

    Certificate verification is always REQUIRED for TLS endpoints — this
    is never downgraded. Returns None for plain redis:// URLs so local
    development configuration is unchanged.
    """
    if redis_url and redis_url.startswith("rediss://"):
        return {"ssl_cert_reqs": ssl.CERT_REQUIRED}
    return None
