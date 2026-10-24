"""Authentication service: Argon2id passwords, opaque server-side sessions.

Security properties (ADR-0008):
- Passwords: Argon2id via argon2-cffi (pinned); encoded hashes only; never
  logged or returned.
- Session tokens: 32 bytes from secrets.token_urlsafe (256-bit entropy);
  only sha256(token) is stored; cookies are HttpOnly.
- CSRF: per-session 32-byte token, stored hashed, returned only via
  GET /auth/csrf to the session owner; mutations must echo it in the
  X-CSRF-Token header (secrets.compare_digest).
- Emails are lowercased/trimmed before lookup and storage.
- Dev-era users (password_hash NULL) simply fail verification; they are
  never auto-assigned passwords and their data is preserved.
"""

import hashlib
import logging
import secrets
import uuid
from datetime import UTC, datetime
from email.utils import parseaddr

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import User, UserSession
from app.models.base import utcnow

logger = logging.getLogger(__name__)
audit = logging.getLogger("audit")

# Uniform failure message — no account enumeration.
INVALID_CREDENTIALS = "Invalid email or password."

# Update last_seen_at at most once per minute per session.
_LAST_SEEN_THROTTLE = 60.0


def normalize_email(raw: str) -> str:
    return parseaddr(raw.strip())[1].lower()


def make_hasher() -> PasswordHasher:
    s = get_settings()
    return PasswordHasher(
        time_cost=s.argon2_time_cost,
        memory_cost=s.argon2_memory_cost,
        parallelism=s.argon2_parallelism,
    )


def hash_password(password: str) -> str:
    return make_hasher().hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Constant-outcome verification; any hash/verification error -> False."""
    try:
        return make_hasher().verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return make_hasher().check_needs_rehash(password_hash)


def _sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def create_user(db: Session, *, email: str, password: str, display_name: str) -> User:
    """Register a user; caller handles IntegrityError for races."""
    user = User(
        email=normalize_email(email),
        password_hash=hash_password(password),
        display_name=display_name.strip()[:64] or normalize_email(email).split("@")[0],
    )
    db.add(user)
    db.commit()
    return user


def find_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == normalize_email(email)))


def _dummy_verify() -> None:
    """Burn one Argon2 verification against a fixed hash so unknown-email
    logins cost the same time as wrong-password logins."""
    verify_password(
        "$argon2id$v=19$m=65536,t=2,p=4$"
        "c2FsdHNhbHRzYWx0c2FsdA$"
        "Zm9vYmFyZm9vYmFyZm9vYmFyZm9vYmFyZm9vYmFyZm9v",
        "timing-equalizer",
    )


def authenticate(db: Session, *, email: str, password: str) -> User | None:
    user = find_user_by_email(db, email)
    if user is None or user.password_hash is None:
        _dummy_verify()
        return None
    if not verify_password(user.password_hash, password):
        return None
    return user


def create_session(db: Session, *, user_id: uuid.UUID) -> tuple[UserSession, str, str]:
    """Returns (row, raw_session_token, raw_csrf_token)."""
    settings = get_settings()
    now = utcnow()
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    session = UserSession(
        user_id=user_id,
        token_hash=_sha256_hex(token),
        csrf_token_hash=_sha256_hex(csrf),
        issued_at=now,
        last_seen_at=now,
        expires_at=datetime.fromtimestamp(
            now.timestamp() + settings.session_absolute_seconds, tz=now.tzinfo
        ),
        created_via="login",
    )
    db.add(session)
    db.commit()
    return session, token, csrf


def _aware(dt: datetime) -> datetime:
    """SQLite reloads timestamps naive; PostgreSQL keeps them aware."""
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def resolve_session(
    db: Session, *, raw_token: str, now: datetime | None = None
) -> UserSession | None:
    """Validate token hash, absolute expiry, inactivity, and revocation.

    Slides last_seen_at (throttled). A cookie's presence alone never
    authorizes anything: every check happens here against the row.
    """
    settings = get_settings()
    now = now or utcnow()
    session = db.scalar(
        select(UserSession).where(UserSession.token_hash == _sha256_hex(raw_token))
    )
    if session is None or session.revoked_at is not None:
        return None
    if now >= _aware(session.expires_at):
        return None
    inactivity = settings.session_inactivity_seconds
    if (now - _aware(session.last_seen_at)).total_seconds() > inactivity:
        return None
    user = db.get(User, session.user_id)
    if user is None:
        return None
    if (now - _aware(session.last_seen_at)).total_seconds() >= _LAST_SEEN_THROTTLE:
        db.execute(
            update(UserSession)
            .where(UserSession.id == session.id)
            .values(last_seen_at=now, updated_at=now)
        )
        db.commit()
    return session


def csrf_matches(session: UserSession, raw_csrf: str) -> bool:
    return secrets.compare_digest(session.csrf_token_hash, _sha256_hex(raw_csrf or ""))


def revoke_session(db: Session, session: UserSession) -> None:
    if session.revoked_at is None:
        session.revoked_at = utcnow()
        db.commit()


def revoke_all_user_sessions(
    db: Session, user_id: uuid.UUID, *, except_id: uuid.UUID | None = None
) -> int:
    conditions = [
        UserSession.user_id == user_id,
        UserSession.revoked_at.is_(None),
    ]
    if except_id is not None:
        conditions.append(UserSession.id != except_id)
    result = db.execute(
        update(UserSession)
        .where(*conditions)
        .values(revoked_at=utcnow(), updated_at=utcnow())
    )
    db.commit()
    return result.rowcount


def list_user_sessions(db: Session, user_id: uuid.UUID) -> list[UserSession]:
    return list(
        db.scalars(
            select(UserSession)
            .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
            .order_by(UserSession.last_seen_at.desc())
        ).all()
    )


def audit_event(event: str, **fields) -> None:
    """Structured audit line. Callers must never pass credentials or tokens."""
    audit.info("audit", extra={"event": event, **fields})
