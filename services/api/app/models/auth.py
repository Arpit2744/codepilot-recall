"""Server-side session model (Phase 5).

Opaque high-entropy tokens are sent as cookies; only a SHA-256 digest of
the token is stored, so a database leak does not yield usable bearer
secrets. CSRF tokens are stored hashed and bound to the session row.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UserSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "user_sessions"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_user_sessions_token_hash"),
        Index("ix_user_sessions_user", "user_id", "revoked_at"),
        Index("ix_user_sessions_expiry", "expires_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # sha256_hex(urlsafe_token) — 256-bit tokens make a plain digest sound.
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # sha256_hex(csrf_token); the raw CSRF token lives only in the client.
    csrf_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Minimal auditing metadata; no raw tokens, no user-agent free-text.
    created_via: Mapped[str] = mapped_column(String(16), default="login", nullable=False)
