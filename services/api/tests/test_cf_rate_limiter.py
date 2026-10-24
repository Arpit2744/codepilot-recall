"""Rate limiter tests (in-memory + Redis backend with a fake client)."""

import pytest

from app.integrations.codeforces.rate_limiter import (
    InMemoryRateLimiter,
    RateLimitTimeout,
    RedisRateLimiter,
)


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds: float):
        self.now += seconds


def test_in_memory_limiter_sleeps_for_remaining_interval():
    clock = FakeClock()
    sleeps = []
    limiter = InMemoryRateLimiter(2.5, sleep=sleeps.append, clock=clock)

    limiter.acquire()  # first call: no wait
    assert sleeps == []

    limiter.acquire()  # 0s elapsed -> must wait the full interval
    assert sleeps == [2.5]


def test_in_memory_limiter_no_wait_after_interval_elapses():
    clock = FakeClock()
    sleeps = []
    limiter = InMemoryRateLimiter(2.5, sleep=sleeps.append, clock=clock)

    limiter.acquire()
    clock.advance(3.0)
    limiter.acquire()
    assert sleeps == []


class FakeRedis:
    """Pretends the slot is busy until released."""

    def __init__(self, busy_times: int):
        self.busy_times = busy_times
        self.calls = 0

    def set(self, _key, _value, nx=None, px=None):
        self.calls += 1
        if self.calls <= self.busy_times:
            return None
        return True


def test_redis_limiter_acquires_after_busy_polls():
    clock = FakeClock()
    sleeps = []
    redis = FakeRedis(busy_times=2)
    limiter = RedisRateLimiter(
        redis, interval_seconds=2.5, sleep=sleeps.append, clock=clock, poll_seconds=0.2
    )

    limiter.acquire()
    assert redis.calls == 3
    assert sleeps == [0.2, 0.2]


def test_redis_limiter_times_out_when_never_free():
    clock = FakeClock()
    redis = FakeRedis(busy_times=10**9)
    limiter = RedisRateLimiter(
        redis,
        interval_seconds=2.5,
        max_wait_seconds=1.0,
        sleep=lambda s: clock.advance(s),
        clock=clock,
        poll_seconds=0.2,
    )

    with pytest.raises(RateLimitTimeout):
        limiter.acquire()
