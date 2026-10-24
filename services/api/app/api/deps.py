"""Request dependencies: session authentication, CSRF, and origin checks.

Phase 5 replaced the X-User-Id development boundary with server-side
session authentication (ADR-0008). There is NO fallback identity: a missing,
expired, revoked, or tampered session is 401 in every environment.

CSRF (synchronizer token): state-changing requests carrying a session
cookie must echo the session's CSRF token in the X-CSRF-Token header
(secrets.compare_digest). Cross-site defense-in-depth: Origin (or Referer
fallback) must match a configured application origin when present — a
browser cross-site request always carries Origin; non-browser clients
without Origin/Referer are not CSRF-exposed and pass.

Cookies: HttpOnly + SameSite=Lax always; Secure + __Host- prefix in
production (fail closed; local HTTP dev uses the plain name).
"""

import uuid
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.services import auth

SESSION_COOKIE = "cpr_session"
SESSION_COOKIE_PROD = "__Host-cpr_session"
CSRF_HEADER = "X-CSRF-Token"


def session_cookie_name() -> str:
    settings = get_settings()
    return SESSION_COOKIE_PROD if settings.environment == "production" else SESSION_COOKIE


def set_session_cookie(response, raw_token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=session_cookie_name(),
        value=raw_token,
        max_age=settings.session_absolute_seconds,
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        path="/",  # host-only: no domain attribute
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(key=session_cookie_name(), path="/")


def validate_browser_origin(request: Request) -> None:
    """Origin/Referer check for state-changing browser requests.

    If Origin is present it must exactly match an allowed origin; when
    Origin is absent, Referer's origin is checked the same way. Requests
    with neither header (non-browser clients) pass — browsers always send
    Origin on cross-site state changes.
    """
    allowed = set(get_settings().cors_origins)
    origin = request.headers.get("Origin")
    if origin is not None:
        if origin in allowed:
            return
        raise HTTPException(status_code=403, detail="Untrusted origin")
    referer = request.headers.get("Referer")
    if referer is not None:
        parsed = urlsplit(referer)
        if f"{parsed.scheme}://{parsed.netloc}" in allowed:
            return
        raise HTTPException(status_code=403, detail="Untrusted referer")


def _resolve_session(request: Request, db: Session):
    raw = request.cookies.get(session_cookie_name())
    if not raw:
        return None
    return auth.resolve_session(db, raw_token=raw)


def get_current_user_id(
    request: Request, db: Annotated[Session, Depends(get_db)]
) -> uuid.UUID:
    """Resolve the authenticated user from the validated server-side session."""
    session = _resolve_session(request, db)
    if session is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    request.state.session_id = session.id
    return session.user_id


def require_csrf(request: Request, db: Annotated[Session, Depends(get_db)]) -> uuid.UUID:
    """Authenticate + enforce the CSRF synchronizer token on mutations."""
    user_id = get_current_user_id(request, db)
    session = _resolve_session(request, db)
    provided = request.headers.get(CSRF_HEADER, "")
    if session is None or not auth.csrf_matches(session, provided):
        raise HTTPException(status_code=403, detail="Invalid or missing CSRF token")
    return user_id


def client_identity(request: Request) -> str:
    """Rate-limit identity: the socket peer, NOT proxy-forwarded headers.

    X-Forwarded-For is only trustworthy behind a configured trusted proxy;
    that deployment assumption is documented. Ignoring it here cannot be
    spoofed into evading or targeting someone else's limit.
    """
    if request.client is None or not request.client.host:
        return "unknown"
    return request.client.host
