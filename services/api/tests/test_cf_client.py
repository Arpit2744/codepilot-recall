"""Codeforces client tests with mocked HTTP (httpx.MockTransport, no network)."""

import httpx
import pytest

from app.core.config import Settings
from app.integrations.codeforces.client import (
    CfApiError,
    CfHandleNotFound,
    CfTransientError,
    CodeforcesApiClient,
)


class LimiterSpy:
    def __init__(self):
        self.calls = 0

    def acquire(self):
        self.calls += 1


def make_client(handler, *, max_retries=2, sleeps=None, limiter=None) -> CodeforcesApiClient:
    settings = Settings(
        cf_backoff_base_seconds=0.0,
        cf_backoff_max_seconds=0.0,
        cf_max_retries=max_retries,
        environment="test",
    )
    return CodeforcesApiClient(
        settings=settings,
        rate_limiter=limiter,
        transport=httpx.MockTransport(handler),
        sleep=(sleeps.append if sleeps is not None else (lambda _s: None)),
        rng=lambda _a, _b: 0.0,
    )


def envelope_ok(result):
    return {"status": "OK", "result": result}


def test_user_info_success():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "handles=tourist" in str(request.url)
        return httpx.Response(200, json=envelope_ok([{"handle": "tourist", "rating": 3900}]))

    client = make_client(handler)
    info = client.get_user_info("tourist")
    assert info["handle"] == "tourist"


def test_user_status_success_and_pagination_params():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(httpx.URL(request.url).params)
        seen.append(params)
        return httpx.Response(200, json=envelope_ok([{"id": 1}]))

    client = make_client(handler)
    page = client.fetch_status_page("tourist", from_=1001, count=1000)
    assert page == [{"id": 1}]
    assert seen[-1]["from"] == "1001"
    assert seen[-1]["count"] == "1000"
    assert seen[-1]["handle"] == "tourist"


def test_handle_not_found_is_permanent_no_retry():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(
            400, json={"status": "FAILED", "comment": "handles: some handles not found"}
        )

    client = make_client(handler)
    with pytest.raises(CfHandleNotFound):
        client.get_user_info("no-such-handle-x")
    assert len(calls) == 1


def test_failed_envelope_raises_and_never_returns_empty_history():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"status": "FAILED", "comment": "unexpected error"})

    client = make_client(handler)
    with pytest.raises(CfApiError) as excinfo:
        client.fetch_status_page("tourist", 1, 100)
    assert "unexpected error" in str(excinfo.value)


def test_malformed_json_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>not json</html>")

    client = make_client(handler)
    with pytest.raises(CfApiError, match="malformed JSON"):
        client.get_user_info("tourist")


def test_transport_error_retries_then_succeeds():
    attempts = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) < 3:
            raise httpx.ConnectError("boom")
        return httpx.Response(200, json=envelope_ok([{"handle": "tourist"}]))

    sleeps = []
    client = make_client(handler, max_retries=3, sleeps=sleeps)
    assert client.get_user_info("tourist")["handle"] == "tourist"
    assert len(attempts) == 3
    assert len(sleeps) == 2  # slept between retries only


def test_transients_exhaust_retries():
    attempts = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        raise httpx.ReadTimeout("too slow")

    client = make_client(handler, max_retries=2)
    with pytest.raises(CfTransientError, match="3 attempts"):
        client.get_user_info("tourist")
    assert len(attempts) == 3


def test_429_honors_retry_after_then_succeeds():
    attempts = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) == 1:
            return httpx.Response(429, headers={"Retry-After": "2"}, json={})
        return httpx.Response(200, json=envelope_ok([{"handle": "tourist"}]))

    sleeps = []
    client = make_client(handler, max_retries=2, sleeps=sleeps)
    client.get_user_info("tourist")
    assert sleeps == [2.0]


def test_5xx_retried_then_succeeds():
    attempts = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) == 1:
            return httpx.Response(502, json={})
        return httpx.Response(200, json=envelope_ok([{"handle": "tourist"}]))

    client = make_client(handler, max_retries=2)
    assert client.get_user_info("tourist")["handle"] == "tourist"
    assert len(attempts) == 2


def test_rate_limiter_runs_before_every_attempt_including_retries():
    attempts = []
    limiter = LimiterSpy()

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        if len(attempts) == 1:
            return httpx.Response(500, json={})
        return httpx.Response(200, json=envelope_ok([{"handle": "tourist"}]))

    client = make_client(handler, max_retries=2, limiter=limiter)
    client.get_user_info("tourist")
    assert limiter.calls == 2


def test_non_list_status_result_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=envelope_ok({"unexpected": "shape"}))

    client = make_client(handler)
    with pytest.raises(CfApiError, match="non-list"):
        client.fetch_status_page("tourist", 1, 100)
