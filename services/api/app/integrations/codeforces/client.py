"""Typed client for the public Codeforces API (https://codeforces.com/apiHelp).

Design notes:
- Public methods only; no API keys and never any Codeforces credentials.
- Every request passes the shared rate limiter first (cross-process gate).
- Transient failures (transport errors, timeouts, 5xx, 429/503 with
  Retry-After) retry with bounded exponential backoff plus jitter.
- Permanent failures (FAILED envelope, other 4xx) never retry.
- A FAILED envelope is an error, never an empty history.
"""

import logging
import random
import time
from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.integrations.codeforces.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class CfApiError(Exception):
    """Permanent Codeforces API failure."""

    def __init__(self, message: str, *, status_code: int | None = None, comment: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.comment = comment


class CfHandleNotFound(CfApiError):
    """The requested handle does not exist (validated via user.info)."""


class CfTransientError(CfApiError):
    """Transient failure exhausted all retries; safe to retry the job later."""


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None  # HTTP-date form: fall back to computed backoff


class CodeforcesApiClient:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        rate_limiter: RateLimiter | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep=time.sleep,
        rng=random.uniform,
    ):
        settings = settings or get_settings()
        self._settings = settings
        self._limiter = rate_limiter
        self._sleep = sleep
        self._rng = rng
        self._http = httpx.Client(
            base_url=settings.cf_api_base_url.rstrip("/"),
            timeout=httpx.Timeout(
                connect=settings.cf_connect_timeout_seconds,
                read=settings.cf_read_timeout_seconds,
                write=10.0,
                pool=10.0,
            ),
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    # ------------------------------------------------------------------ API

    def get_user_info(self, handle: str) -> dict[str, Any]:
        """Fetch public profile info; raises CfHandleNotFound for bad handles."""
        result = self._request("user.info", {"handles": handle})
        if not isinstance(result, list) or not result:
            raise CfApiError("user.info returned no results", status_code=200)
        return result[0]

    def fetch_status_page(self, handle: str, from_: int, count: int) -> list[dict[str, Any]]:
        """One page of `user.status` (newest-first). Empty list = end of history."""
        params = {"handle": handle, "from": str(from_), "count": str(count)}
        result = self._request("user.status", params)
        if not isinstance(result, list):
            raise CfApiError("user.status returned a non-list result", status_code=200)
        return result

    # ------------------------------------------------------------ internals

    def _backoff_seconds(self, attempt: int, retry_after: float | None) -> float:
        s = self._settings
        if retry_after is not None:
            # Honor the server's requested delay, bounded by a generous hard cap.
            return min(retry_after, 300.0)
        raw = s.cf_backoff_base_seconds * (2**attempt) + self._rng(0, s.cf_backoff_base_seconds)
        return min(raw, s.cf_backoff_max_seconds)

    def _request(self, path: str, params: dict[str, str]) -> Any:
        s = self._settings
        last_error: str = "unreachable"
        for attempt in range(s.cf_max_retries + 1):
            if self._limiter is not None:
                self._limiter.acquire()
            try:
                response = self._http.get(f"/{path}", params=params)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = f"transport error: {exc}"
                self._sleep_retry(attempt, last_error)
                continue

            status = response.status_code

            if status in (429, 503):
                wait = _parse_retry_after(response.headers.get("Retry-After"))
                last_error = f"rate limited (HTTP {status})"
                self._sleep_retry(attempt, last_error, retry_after=wait)
                continue

            if status >= 500:
                last_error = f"server error (HTTP {status})"
                self._sleep_retry(attempt, last_error)
                continue

            try:
                payload = response.json()
            except ValueError:
                raise CfApiError(f"malformed JSON from {path}", status_code=status) from None

            if isinstance(payload, dict) and payload.get("status") == "OK":
                return payload.get("result")

            comment = payload.get("comment") if isinstance(payload, dict) else None
            message = comment or f"unsuccessful response (HTTP {status})"
            if isinstance(comment, str) and "not found" in comment.lower():
                raise CfHandleNotFound(message, status_code=status, comment=comment)
            raise CfApiError(f"{path} failed: {message}", status_code=status, comment=comment)

        raise CfTransientError(
            f"{path} failed after {s.cf_max_retries + 1} attempts: {last_error}"
        )

    def _sleep_retry(self, attempt: int, reason: str, *, retry_after: float | None = None) -> None:
        wait = self._backoff_seconds(attempt, retry_after)
        logger.warning(
            "codeforces retry attempt=%d wait=%.2fs reason=%s", attempt + 1, wait, reason
        )
        self._sleep(wait)
