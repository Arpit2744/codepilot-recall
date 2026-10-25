"""Authentication endpoints: register, login, logout, me, csrf, sessions."""

import hashlib
import secrets
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import (
    clear_session_cookie,
    client_identity,
    get_current_user_id,
    require_csrf,
    set_session_cookie,
    validate_browser_origin,
)
from app.core.config import get_settings
from app.core.db import get_db
from app.core.rate_limit import RateLimitExceeded, RateLimitUnavailable, enforce
from app.models import User, UserSession
from app.schemas.auth import (
    AuthResponse,
    AuthUser,
    CsrfResponse,
    LoginRequest,
    RegisterRequest,
    RevokeAllResponse,
    SessionInfo,
    SessionListResponse,
)
from app.services import auth

router = APIRouter(prefix="/auth", tags=["auth"])

GENERIC_LOGIN_ERROR = auth.INVALID_CREDENTIALS


def _rate_limit_response(exc: RateLimitExceeded) -> HTTPException:
    detail = HTTPException(
        status_code=429, detail=f"Too many attempts; retry after {exc.retry_after_seconds}s"
    )
    detail.headers = {"Retry-After": str(exc.retry_after_seconds)}
    return detail


def _user_out(user: User) -> AuthUser:
    return AuthUser(
        id=user.id, email=user.email, display_name=user.display_name, created_at=user.created_at
    )


@router.post("/register", response_model=AuthResponse, status_code=201)
def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
):
    """Create an account and open a session.

    No email verification or password reset exists yet (no mail provider);
    both flows are explicitly deferred (ADR-0008).
    """
    validate_browser_origin(request)
    identity = client_identity(request)
    try:
        enforce("register", f"ip:{identity}")
    except RateLimitExceeded as exc:
        auth.audit_event("registration.rate_limited", ip=identity)
        raise _rate_limit_response(exc) from exc
    except RateLimitUnavailable as exc:
        auth.audit_event("registration.limiter_unavailable", ip=identity)
        raise HTTPException(
            status_code=503, detail="Registration temporarily unavailable"
        ) from exc

    settings = get_settings()
    normalized = auth.normalize_email(payload.email)
    # Allowlist entries are normalized the same way as the incoming address,
    # so case/format variations in the dashboard value still match.
    allowlisted = {auth.normalize_email(e) for e in settings.beta_allowed_emails}
    if settings.beta_allowed_emails and normalized not in allowlisted:
        auth.audit_event("registration.rejected_not_invited")
        # Generic message: do not disclose whether any address is on the list.
        raise HTTPException(
            status_code=403,
            detail="Registration is currently limited to invited beta testers.",
        )

    try:
        user = auth.create_user(
            db,
            email=payload.email,
            password=payload.password,
            display_name=payload.display_name or "",
        )
    except IntegrityError:
        db.rollback()
        auth.audit_event("registration.duplicate")
        raise HTTPException(
            status_code=409, detail="An account with this email already exists"
        ) from None

    session, raw_token, raw_csrf = auth.create_session(db, user_id=user.id)
    set_session_cookie(response, raw_token)
    auth.audit_event("registration.success", user_id=str(user.id))
    return AuthResponse(user=_user_out(user), csrf_token=raw_csrf)


@router.post("/login", response_model=AuthResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
):
    validate_browser_origin(request)
    identity = client_identity(request)
    normalized = auth.normalize_email(payload.email)
    try:
        enforce("login_ip", f"ip:{identity}")
        enforce("login_email", f"email:{normalized}")
    except RateLimitExceeded as exc:
        auth.audit_event("login.rate_limited", ip=identity)
        raise _rate_limit_response(exc) from exc
    except RateLimitUnavailable as exc:
        auth.audit_event("login.limiter_unavailable", ip=identity)
        raise HTTPException(status_code=503, detail="Login temporarily unavailable") from exc

    user = auth.authenticate(db, email=payload.email, password=payload.password)
    if user is None:
        auth.audit_event("login.failure", ip=identity)
        raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR)

    session, raw_token, raw_csrf = auth.create_session(db, user_id=user.id)
    set_session_cookie(response, raw_token)
    auth.audit_event("login.success", user_id=str(user.id), ip=identity)
    return AuthResponse(user=_user_out(user), csrf_token=raw_csrf)


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    user_id: Annotated[uuid.UUID, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
):
    """Revoke the current session server-side and expire the cookie."""
    session = db.get(UserSession, request.state.session_id)
    if session is not None:
        auth.revoke_session(db, session)
        auth.audit_event("logout", user_id=str(user_id), session_id=str(session.id))
    clear_session_cookie(response)


@router.get("/me", response_model=AuthUser)
def me(
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return _user_out(user)


@router.get("/csrf", response_model=CsrfResponse)
def csrf(
    request: Request,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    """Mint the CSRF token for the authenticated session.

    Only the sha256 is stored, so each call mints a fresh token (the
    previous one is invalidated). Served solely to the cookie-authenticated
    owner in the response body — never in URLs.
    """
    session = db.get(UserSession, request.state.session_id)
    if session is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    raw_csrf = secrets.token_urlsafe(32)
    session.csrf_token_hash = hashlib.sha256(raw_csrf.encode("utf-8")).hexdigest()
    db.commit()
    return CsrfResponse(csrf_token=raw_csrf)


@router.get("/sessions", response_model=SessionListResponse)
def list_sessions(
    request: Request,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    current_id = getattr(request.state, "session_id", None)
    return SessionListResponse(
        sessions=[
            SessionInfo(
                id=s.id,
                issued_at=s.issued_at,
                last_seen_at=s.last_seen_at,
                expires_at=s.expires_at,
                created_via=s.created_via,
                current=s.id == current_id,
            )
            for s in auth.list_user_sessions(db, user_id)
        ]
    )


@router.post("/sessions/revoke-all", response_model=RevokeAllResponse)
def revoke_all(
    request: Request,
    user_id: Annotated[uuid.UUID, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
):
    """Revoke every session for the account, including the current one."""
    validate_browser_origin(request)
    revoked = auth.revoke_all_user_sessions(db, user_id)
    auth.audit_event("sessions.revoked_all", user_id=str(user_id), count=revoked)
    return RevokeAllResponse(revoked=revoked)