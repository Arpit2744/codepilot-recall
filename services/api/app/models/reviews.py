"""Review sessions and FSRS memory states (Phase 3).

Ownership: every row carries `user_id`; queries filter by it. Scheduling
timestamps are timezone-aware UTC instants; presentation converts to the
user's timezone (ADR-0003). The Codeforces acceptance that created the
underlying `user_problems` row is NOT a review — memory states exist only
after explicit review outcomes (ADR-0006).
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.codeforces import JSONType

REVIEW_OUTCOMES = ("again", "hard", "good", "easy")
REVIEW_STATUSES = ("pending", "completed")
HELP_LEVELS = ("none", "hint", "editorial")


class ReviewSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One review attempt of a solved problem; completion is idempotent."""

    __tablename__ = "review_sessions"
    __table_args__ = (Index("ix_review_sessions_user_completed", "user_id", "completed_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_problem_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_problems.id", ondelete="CASCADE"), nullable=False
    )

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)

    outcome: Mapped[str | None] = mapped_column(String(8))
    independent: Mapped[bool | None] = mapped_column(Boolean)
    help_level: Mapped[str | None] = mapped_column(String(16))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)


class MemoryState(TimestampMixin, UUIDPrimaryKeyMixin, Base):
    """FSRS scheduling state per (user, problem); unique per user_problem."""

    __tablename__ = "memory_states"
    __table_args__ = (
        UniqueConstraint("user_problem_id", name="uq_memory_states_user_problem"),
        Index("ix_memory_states_due", "due_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_problem_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_problems.id", ondelete="CASCADE"), nullable=False
    )

    # Full serialized FSRS state: {"version", "scheduler", "card", "last_log"}.
    scheduler_state: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    scheduler_version: Mapped[str] = mapped_column(String(32), nullable=False)

    last_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    stability: Mapped[float | None] = mapped_column(Float)
    difficulty: Mapped[float | None] = mapped_column(Float)
    repetitions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lapses: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
