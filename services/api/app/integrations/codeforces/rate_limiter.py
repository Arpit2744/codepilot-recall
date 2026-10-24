"""Shared rate limiting for the Codeforces API.

The limit is coordinated across processes (workers + beat), not per-process:
production uses a Redis key with TTL as a cross-process gate; tests use an
in-memory implementation with an injectable clock so no Redis is needed.
"""

import threading
import time
from typing import Protocol

from redis import Redis


class RateLimitTimeout(Exception):
    """Could not acquire the rate-limit slot within the allowed wait."""


class RateLimiter(Protocol):
    def acquire(self) -> None: ...


class InMemoryRateLimiter:
    """Sleep-based limiter for single-process use (tests, local dev)."""

    def __init__(self, interval_seconds: float, sleep=time.sleep, clock=time.monotonic):
        self._interval = interval_seconds
        self._sleep = sleep
        self._clock = clock
        self._lock = threading.Lock()
        self._last: float | None = None

    def acquire(self) -> None:
        with self._lock:
            now = self._clock()
            if self._last is not None:
                wait = self._interval - (now - self._last)
                if wait > 0:
                    self._sleep(wait)
            self._last = self._clock()


class RedisRateLimiter:
    """Cross-process limiter: SET NX PX holds the slot for one interval."""

    def __init__(
        self,
        client: Redis,
        interval_seconds: float,
        key: str = "cf:api:ratelimit",
        max_wait_seconds: float = 300.0,
        poll_seconds: float = 0.2,
        sleep=time.sleep,
        clock=time.monotonic,
    ):
        self._client = client
        self._interval_ms = max(1, int(interval_seconds * 1000))
        self._key = key
        self._max_wait = max_wait_seconds
        self._poll = poll_seconds
        self._sleep = sleep
        self._clock = clock

    def acquire(self) -> None:
        deadline = self._clock() + self._max_wait
        while True:
            acquired = self._client.set(self._key, "1", nx=True, px=self._interval_ms)
            if acquired:
                return
            if self._clock() >= deadline:
                raise RateLimitTimeout(
                    f"could not acquire rate-limit slot {self._key!r} "
                    f"within {self._max_wait}s"
                )
            self._sleep(self._poll)


def build_rate_limiter(redis_url: str | None, interval_seconds: float) -> RateLimiter:
    """Redis-backed limiter when a URL is configured; in-memory otherwise."""
    if redis_url:
        return RedisRateLimiter(Redis.from_url(redis_url), interval_seconds)
    return InMemoryRateLimiter(interval_seconds)
