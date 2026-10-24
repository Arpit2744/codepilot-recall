"""User account model. Authentication flows arrive in Phase 5."""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    # Local password auth lands in Phase 5; stays NULL until a password is set.
    password_hash: Mapped[str | None] = mapped_column(String(255), default=None)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    # IANA timezone name; drives heatmap calendar-day bucketing.
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
