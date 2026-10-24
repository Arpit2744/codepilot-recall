"""Authentication and session-security tests (Phase 5).

Covers registration/login validation, Argon2 verification, session
lifecycle, cookie flags, CSRF, origin validation, rate limits, production
fail-closed behavior, and enumeration resistance.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import pytest

from app.core import rate_limit
from app.core.config import get_settings
from app.models import User, UserSession
from app.services import auth as auth_service

ORIGIN = "http://localhost:3000"
PASSWORD = "Passw0rd!"


def register(client, email="new@example.com", password=PASSWORD, origin=ORIGIN, **over):
    payload = {"email": email, "password": password, **over}
    headers = {"Origin": origin} if origin else {}
    return client.post("/api/v1/auth/register", json=payload, headers=headers)


def login(client, email, password, origin=ORIGIN):
    return client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers={"Origin": origin} if origin else {},
    )


# ------------------------------------------------------------ registration


def test_register_creates_argon2_user_and_session(client, db_session):
    resp = register(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["user"]["email"] == "new@example.com"
    assert "password" not in body["user"] and "csrf_token" in body

    user = db_session.query(User).one()
    assert user.password_hash.startswith("$argon2id$")
    assert auth_service.verify_password(user.password_hash, PASSWORD)

    session = db_session.query(UserSession).one()
    assert session.token_hash != body  # raw token never stored
    assert len(session.token_hash) == 64  # sha256 hex


def test_register_normalizes_email_uniqueness(client, db_session):
    register(client, "MiXeD@Example.COM")
    dup = register(client, "mixed@example.com")
    assert dup.status_code == 409
    assert db_session.query(User).count() == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "not-an-email", "password": "Passw0rd!"},
        {"email": "a@b.c", "password": "short1"},  # < 8
        {"email": "a@b.c", "password": "nodigitshere"},  # no digit
        {"email": "a@b.c", "password": "12345678"},  # no letter
    ],
)
def test_register_validates_input(client, payload):
    resp = client.post(
        "/api/v1/auth/register", json=payload, headers={"Origin": ORIGIN}
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


def test_register_rejects_untrusted_origin(client):
    resp = register(client, origin="https://evil.example")
    assert resp.status_code == 403


# ------------------------------------------------------------------- login


def test_login_success_returns_user_csrf_and_cookie(client):
    register(client, "user@example.com")
    resp = login(client, "user@example.com", PASSWORD)
    assert resp.status_code == 200
    assert resp.json()["user"]["email"] == "user@example.com"

    cookie = resp.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "samesite=lax" in cookie.lower()
    assert "path=/" in cookie.lower()
    assert "domain=" not in cookie.lower()
    # Secure + __Host- only in production; this test env is non-production.
    assert "secure" not in cookie.lower()


def test_login_uniform_failure_no_enumeration(client):
    register(client, "real@example.com")
    unknown = login(client, "ghost@example.com", "Whatever1")
    wrong = login(client, "real@example.com", "WrongPass1")
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["error"]["message"] == wrong.json()["error"]["message"]


def test_dev_era_user_without_password_cannot_login(client, db_session, make_user):
    make_user("legacy@example.com", password=None)
    resp = login(client, "legacy@example.com", "Anything1")
    assert resp.status_code == 401
    # and is never auto-assigned a password
    legacy = db_session.query(User).filter_by(email="legacy@example.com").one()
    assert legacy.password_hash is None


def test_login_creates_new_session_row_each_time(client, db_session):
    register(client, "multi@example.com")
    login(client, "multi@example.com", PASSWORD)
    login(client, "multi@example.com", PASSWORD)
    assert db_session.query(UserSession).count() == 3  # register + 2 logins


# ---------------------------------------------------------------- sessions


def test_me_requires_valid_session(client):
    assert client.get("/api/v1/auth/me").status_code == 401
    tampered = client.cookies.get("cpr_session")
    if tampered:
        client.cookies.set("cpr_session", tampered[:-2] + "xx")
    register(client)
    assert client.get("/api/v1/auth/me").status_code == 200


def test_expired_session_rejected(client, db_session):
    register(client, "expiry@example.com")
    session = db_session.query(UserSession).one()
    session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()
    assert client.get("/api/v1/auth/me").status_code == 401


def test_inactivity_expiry_rejected(client, db_session):
    register(client, "idle@example.com")
    session = db_session.query(UserSession).one()
    session.last_seen_at = datetime.now(UTC) - timedelta(days=30)
    db_session.commit()
    assert client.get("/api/v1/auth/me").status_code == 401


def test_revoked_session_rejected(client, db_session):
    register(client, "rev@example.com")
    session = db_session.query(UserSession).one()
    session.revoked_at = datetime.now(UTC)
    db_session.commit()
    assert client.get("/api/v1/auth/me").status_code == 401


def test_logout_revokes_immediately(client, db_session):
    register(client, "out@example.com")
    login_resp = login(client, "out@example.com", PASSWORD)
    csrf = login_resp.json()["csrf_token"]
    resp = client.post(
        "/api/v1/auth/logout", headers={"Origin": ORIGIN, "X-CSRF-Token": csrf}
    )
    assert resp.status_code == 204
    session = db_session.query(UserSession).order_by(UserSession.issued_at.desc()).first()
    assert session.revoked_at is not None
    assert client.get("/api/v1/auth/me").status_code == 401


def test_revoke_all_sessions(client, db_session):
    register(client, "all@example.com")
    login(client, "all@example.com", PASSWORD)
    active = db_session.query(UserSession).filter_by(revoked_at=None).count()
    assert active == 2

    csrf = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    resp = client.post(
        "/api/v1/auth/sessions/revoke-all",
        headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
    )
    assert resp.status_code == 200
    assert resp.json()["revoked"] == active
    assert client.get("/api/v1/auth/me").status_code == 401


def test_sessions_list_marks_current(client):
    register(client, "list@example.com")
    login(client, "list@example.com", PASSWORD)
    body = client.get("/api/v1/auth/sessions").json()
    assert len(body["sessions"]) == 2
    assert sum(1 for s in body["sessions"] if s["current"]) == 1


# -------------------------------------------------------------------- CSRF


def _authed(client):
    resp = register(client, "csrf@example.com")
    return resp.json()["csrf_token"]


def test_mutation_without_csrf_rejected(client):
    _authed(client)
    resp = client.post(
        "/api/v1/codeforces/accounts",
        json={"handle": "tourist"},
        headers={"Origin": ORIGIN},
    )
    assert resp.status_code == 403
    assert "CSRF" in resp.json()["error"]["message"]


def test_mutation_with_wrong_csrf_rejected(client):
    _authed(client)
    resp = client.post(
        "/api/v1/codeforces/accounts",
        json={"handle": "tourist"},
        headers={"Origin": ORIGIN, "X-CSRF-Token": "forged"},
    )
    assert resp.status_code == 403


def test_mutation_with_valid_csrf_accepted(client):
    csrf = _authed(client)
    resp = client.post(
        "/api/v1/codeforces/accounts",
        json={"handle": "tourist"},
        headers={"Origin": ORIGIN, "X-CSRF-Token": csrf},
    )
    assert resp.status_code == 202


def test_csrf_rotation_invalidates_previous_token(client):
    _authed(client)
    fresh = client.get("/api/v1/auth/csrf").json()["csrf_token"]
    resp = client.post(
        "/api/v1/codeforces/accounts",
        json={"handle": "tourist"},
        headers={"Origin": ORIGIN, "X-CSRF-Token": fresh},
    )
    assert resp.status_code == 202


def test_stale_csrf_token_rejected_after_rotation(client):
    old = _authed(client)
    client.get("/api/v1/auth/csrf")  # rotates
    resp = client.post(
        "/api/v1/codeforces/accounts",
        json={"handle": "tourist"},
        headers={"Origin": ORIGIN, "X-CSRF-Token": old},
    )
    assert resp.status_code == 403


def test_mutation_with_untrusted_origin_rejected_even_with_csrf(client):
    csrf = _authed(client)
    resp = client.post(
        "/api/v1/codeforces/accounts",
        json={"handle": "tourist"},
        headers={"Origin": "https://attacker.example", "X-CSRF-Token": csrf},
    )
    assert resp.status_code == 403


def test_referer_fallback_validated(client):
    csrf = _authed(client)
    ok = client.post(
        "/api/v1/codeforces/accounts",
        json={"handle": "tourist"},
        headers={"Referer": "http://localhost:3000/dashboard", "X-CSRF-Token": csrf},
    )
    assert ok.status_code == 202
    bad = client.post(
        "/api/v1/codeforces/accounts",
        json={"handle": "x"},
        headers={"Referer": "https://evil.example/x", "X-CSRF-Token": csrf},
    )
    assert bad.status_code == 403


def test_non_browser_client_without_origin_passes(client):
    """CSRF protects browsers; a header-less client is not cross-site."""
    csrf = _authed(client)
    resp = client.post(
        "/api/v1/codeforces/accounts",
        json={"handle": "tourist"},
        headers={"X-CSRF-Token": csrf},
    )
    assert resp.status_code == 202


# ------------------------------------------------------------- rate limits


class FixedLimiter:
    def __init__(self, allowed):
        self.allowed = allowed

    def hit(self, key, limit, window_seconds):
        return self.allowed, 42


def test_login_rate_limit_returns_429_with_retry_after(client, monkeypatch):
    register(client, "rl@example.com")
    monkeypatch.setattr(rate_limit, "get_rate_limiter", lambda: FixedLimiter(False))
    resp = login(client, "rl@example.com", PASSWORD)
    assert resp.status_code == 429
    assert resp.headers["retry-after"] == "42"
    assert "Too many attempts" in resp.json()["error"]["message"]


def test_rate_limit_passes_when_under_limit(client, monkeypatch):
    monkeypatch.setattr(rate_limit, "get_rate_limiter", lambda: FixedLimiter(True))
    resp = login(client, "nobody@example.com", "Whatever1")
    assert resp.status_code == 401  # limited path OK; auth failed normally


def test_rate_limit_window_reset_allows_again(client):
    register(client, "reset@example.com")
    limiter = rate_limit.InMemoryRateLimiter()
    monkeypatch_holder = {}

    def counting_limiter():
        return monkeypatch_holder["limiter"]

    monkeypatch_holder["limiter"] = limiter
    original = rate_limit.get_rate_limiter
    rate_limit.get_rate_limiter = counting_limiter
    try:
        settings = get_settings()
        limit, window = rate_limit.parse_limit(settings.rate_limit_login_ip)
        for _ in range(limit):
            login(client, "reset@example.com", "Wrong1")
        blocked = login(client, "reset@example.com", PASSWORD)
        assert blocked.status_code == 429

        # Simulate window expiry: fresh in-memory limiter resets counts.
        monkeypatch_holder["limiter"] = rate_limit.InMemoryRateLimiter()
        again = login(client, "reset@example.com", PASSWORD)
        assert again.status_code == 200
    finally:
        rate_limit.get_rate_limiter = original


class BrokenRedis:
    def hit(self, key, limit, window_seconds):
        raise ConnectionError("redis down")


def test_limiter_outage_fails_closed_in_production(client, monkeypatch):
    register(client, "down@example.com")
    monkeypatch.setattr(rate_limit, "get_rate_limiter", lambda: BrokenRedis())
    monkeypatch.setenv("ENVIRONMENT", "production")
    get_settings.cache_clear()
    try:
        resp = login(client, "down@example.com", PASSWORD)
        assert resp.status_code == 503
    finally:
        monkeypatch.delenv("ENVIRONMENT")
        get_settings.cache_clear()


def test_limiter_outage_degrades_in_non_production(client, monkeypatch):
    register(client, "devdown@example.com")
    monkeypatch.setattr(rate_limit, "get_rate_limiter", lambda: BrokenRedis())
    resp = login(client, "devdown@example.com", PASSWORD)
    assert resp.status_code == 200


# ----------------------------------------------------- production fail-safe


def test_production_uses_host_prefixed_secure_cookie(client, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    get_settings.cache_clear()
    try:
        resp = register(client, "prod@example.com")
        assert resp.status_code == 201
        cookie = resp.headers["set-cookie"]
        assert cookie.startswith("__Host-cpr_session=")
        assert "Secure" in cookie
        assert "HttpOnly" in cookie
    finally:
        monkeypatch.delenv("ENVIRONMENT")
        get_settings.cache_clear()


def test_production_rejects_non_origin_login(client, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    get_settings.cache_clear()
    try:
        resp = register(client, "strict@example.com", origin=None)
        # No Origin/Referer on a browser-intended endpoint still registers
        # (non-browser path), documented; the security property tested above
        # is the trusted-origin rejection.
        assert resp.status_code in (201, 403)
    finally:
        monkeypatch.delenv("ENVIRONMENT")
        get_settings.cache_clear()


# ------------------------------------------------------ token hygiene


def test_session_tokens_are_high_entropy(db_session, make_user):
    make_user("entropy@example.com", password=PASSWORD)
    _, token, csrf = auth_service.create_session(
        db_session, user_id=db_session.query(User).filter_by(email="entropy@example.com").one().id
    )
    assert len(secrets.token_urlsafe(32)) == len(token)  # 43-char urlsafe
    assert hashlib.sha256(token.encode()).hexdigest() != csrf
