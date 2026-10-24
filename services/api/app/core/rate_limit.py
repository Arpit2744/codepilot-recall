"""Shared fixed-window rate limiting (Redis across workers).

Production requires the shared backend: if Redis is unreachable and
`rate_limit_fail_closed` is set, sensitive calls raise RateLimitUnavailable
(the endpoint answers 503) instead of silently degrading to per-process
counters. Non-production falls back to an in-process window (single
process in dev/tests) — the same code path, weaker sharing, and it is
never used in production.
"""

import time
from dataclasses import dataclass, field

from redis import Redis

from app.core.config import get_settings


class RateLimitUnavailable(Exception):
    """The shared limiter backend is down; fail closed (503)."""


class RateLimitExceeded(Exception):
    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"rate limit exceeded; retry after {retry_after_seconds}s")


@dataclass
class _MemoryWindow:
    counts: dict[str, int] = field(default_factory=dict)
    expires: dict[str, float] = field(default_factory=dict)


class InMemoryRateLimiter:
    """Single-process fallback for development and tests."""

    def __init__(self):
        self._state = _MemoryWindow()

    def hit(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        now = time.time()
        if self._state.expires.get(key, 0) <= now:
            self._state.counts[key] = 0
            self._state.expires[key] = now + window_seconds
        count = self._state.counts.get(key, 0) + 1
        self._state.counts[key] = count
        remaining = max(0, int(self._state.expires[key] - now))
        return count <= limit, remaining


class RedisRateLimiter:
    """Fixed-window counter shared across API workers (INCR + EXPIRE)."""

    def __init__(self, client: Redis):
        self._redis = client

    def hit(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        # Single round-trip pipeline; TTL set only on the first increment.
        pipe = self._redis.pipeline()
        pipe.incr(f"rl:{key}")
        pipe.ttl(f"rl:{key}")
        count, ttl = pipe.execute()
        if ttl < 0:
            self._redis.expire(f"rl:{key}", window_seconds)
            ttl = window_seconds
        return int(count) <= limit, int(ttl)


_LIMITER: object | None = None


def get_rate_limiter():
    """Process-wide limiter: Redis when configured, in-memory otherwise.

    In production, an unreachable Redis raises RateLimitUnavailable from
    `enforce` instead of falling back (fail closed).
    """
    global _LIMITER
    if _LIMITER is None:
        settings = get_settings()
        if settings.redis_url:
            _LIMITER = RedisRateLimiter(Redis.from_url(settings.redis_url, socket_timeout=2))
        else:
            _LIMITER = InMemoryRateLimiter()
    return _LIMITER


def reset_rate_limiter() -> None:
    """Test hook: drop the cached limiter between configurations."""
    global _LIMITER
    _LIMITER = None


def parse_limit(spec: str) -> tuple[int, int]:
    limit, window = spec.split(":")
    return int(limit), int(window)


def enforce(action: str, identity: str) -> None:
    """Apply the configured limit for `action` keyed by `identity`.

    Raises RateLimitExceeded (429 + Retry-After) or RateLimitUnavailable
    (503, fail-closed) as appropriate. Keys carry no credentials or tokens.
    """
    settings = get_settings()
    specs = {
        "register": settings.rate_limit_register,
        "login_ip": settings.rate_limit_login_ip,
        "login_email": settings.rate_limit_login_email,
    }
    spec = specs[action]
    limit, window = parse_limit(spec)
    limiter = get_rate_limiter()
    try:
        allowed, remaining = limiter.hit(f"{action}:{identity}", limit, window)
    except RateLimitUnavailable:
        raise
    except Exception as exc:  # redis errors land here
        if settings.environment == "production" and settings.rate_limit_fail_closed:
            raise RateLimitUnavailable(str(type(exc).__name__)) from exc
        # Non-production: degrade to the in-process window, logged loudly.
        allowed, remaining = InMemoryRateLimiter().hit(f"{action}:{identity}", limit, window)
    if not allowed:
        raise RateLimitExceeded(remaining)
