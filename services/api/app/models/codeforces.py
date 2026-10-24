"""Codeforces integration models: accounts, problems, submissions, solves, jobs."""

from datetime import datetime
from typing import Any
from uuid import UUID  # noqa: F401  (re-exported for typing convenience)

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

#: Portable JSON column: JSONB on PostgreSQL, JSON elsewhere (tests use SQLite).
JSONType = JSON().with_variant(JSONB(), "postgresql")


class CfAccount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A Codeforces handle linked to a user."""

    __tablename__ = "cf_accounts"
    __table_args__ = (
        UniqueConstraint("user_id", "handle_lower", name="uq_cf_accounts_user_handle"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Codeforces handles are public data: multiple app users may track the
    # same handle (ADR-0009). Uniqueness is per owning user.
    handle: Mapped[str] = mapped_column(String(24), nullable=False)
    handle_lower: Mapped[str] = mapped_column(String(24), nullable=False)

    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Sync cursor: {"last_seen_submission_id": int, "last_seen_submitted_at": iso}
    sync_cursor: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    last_sync_error: Mapped[str | None] = mapped_column(Text)


class Problem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A canonical Codeforces problem shared across users."""

    __tablename__ = "problems"

    # "{contestId}-{index}" or "ps:{problemsetName}:{slug(name)}" for gym-style
    # problems without a contest id. Identity never changes once assigned.
    canonical_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)

    contest_id: Mapped[int | None] = mapped_column(Integer)
    problem_index: Mapped[str | None] = mapped_column(String(8))
    problemset_name: Mapped[str | None] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    rating: Mapped[int | None] = mapped_column(Integer)
    tags: Mapped[list[str]] = mapped_column(JSONType, default=list, nullable=False)
    url: Mapped[str | None] = mapped_column(String(512))


class Submission(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One source submission on an account; verdicts may refresh on re-sync."""

    __tablename__ = "submissions"
    __table_args__ = (
        UniqueConstraint(
            "cf_account_id", "cf_submission_id", name="uq_submissions_account_source_id"
        ),
        Index("ix_submissions_problem_submitted", "problem_id", "submitted_at"),
        Index("ix_submissions_account_submitted", "cf_account_id", "submitted_at"),
    )

    cf_account_id: Mapped[UUID] = mapped_column(
        ForeignKey("cf_accounts.id", ondelete="CASCADE"), nullable=False
    )
    cf_submission_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    problem_id: Mapped[UUID] = mapped_column(
        ForeignKey("problems.id", ondelete="RESTRICT"), nullable=False
    )

    verdict: Mapped[str | None] = mapped_column(String(32))
    programming_language: Mapped[str | None] = mapped_column(String(64))
    passed_test_count: Mapped[int | None] = mapped_column(Integer)
    time_consumed_millis: Mapped[int | None] = mapped_column(Integer)
    memory_consumed_bytes: Mapped[int | None] = mapped_column(BigInteger)
    # Source creation timestamp (creationTimeSeconds) — the only time source.
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Optional normalized source metadata (e.g. author.participationType).
    source_meta: Mapped[dict[str, Any] | None] = mapped_column(JSONType)


class UserProblem(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Per-user rollup for a solved problem; derived, never client-supplied."""

    __tablename__ = "user_problems"
    __table_args__ = (
        UniqueConstraint("user_id", "problem_id", name="uq_user_problems_user_problem"),
        Index("ix_user_problems_user_first_solved", "user_id", "first_solved_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    problem_id: Mapped[UUID] = mapped_column(
        ForeignKey("problems.id", ondelete="RESTRICT"), nullable=False
    )

    # Earliest known accepted submission; may only ever move EARLIER as older
    # data is discovered — revisions never overwrite it.
    first_solved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_solved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    first_solve_source: Mapped[str] = mapped_column(
        String(32), default="codeforces", nullable=False
    )
    # A Codeforces acceptance alone is not proof of independent recall (Phase 3).
    independent_solve_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class SyncJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Lifecycle record for one synchronization run of one account."""

    __tablename__ = "sync_jobs"
    __table_args__ = (Index("ix_sync_jobs_account_created", "cf_account_id", "created_at"),)

    JOB_TYPES = ("historical", "incremental", "reconcile")
    STATUSES = ("pending", "running", "succeeded", "failed", "cancelled")

    cf_account_id: Mapped[UUID] = mapped_column(
        ForeignKey("cf_accounts.id", ondelete="CASCADE"), nullable=False
    )
    job_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_summary: Mapped[str | None] = mapped_column(Text)
    # Progress: {"pages_fetched": int, "submissions_seen": int, "new_submissions": int}
    progress: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
