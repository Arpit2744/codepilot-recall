"""review sessions and FSRS memory states (Phase 3)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-24
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "review_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("user_problem_id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("outcome", sa.String(length=8), nullable=True),
        sa.Column("independent", sa.Boolean(), nullable=True),
        sa.Column("help_level", sa.String(length=16), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE", name="fk_review_sessions_user_id"
        ),
        sa.ForeignKeyConstraint(
            ["user_problem_id"],
            ["user_problems.id"],
            ondelete="CASCADE",
            name="fk_review_sessions_user_problem_id",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_review_sessions"),
    )
    op.create_index("ix_review_sessions_user_id", "review_sessions", ["user_id"])
    op.create_index(
        "ix_review_sessions_user_completed", "review_sessions", ["user_id", "completed_at"]
    )

    op.create_table(
        "memory_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("user_problem_id", sa.Uuid(), nullable=False),
        sa.Column("scheduler_state", _JSON, nullable=False),
        sa.Column("scheduler_version", sa.String(length=32), nullable=False),
        sa.Column("last_review_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stability", sa.Float(), nullable=True),
        sa.Column("difficulty", sa.Float(), nullable=True),
        sa.Column("repetitions", sa.Integer(), nullable=False),
        sa.Column("lapses", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE", name="fk_memory_states_user_id"
        ),
        sa.ForeignKeyConstraint(
            ["user_problem_id"],
            ["user_problems.id"],
            ondelete="CASCADE",
            name="fk_memory_states_user_problem_id",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_memory_states"),
        sa.UniqueConstraint("user_problem_id", name="uq_memory_states_user_problem"),
    )
    op.create_index("ix_memory_states_user_id", "memory_states", ["user_id"])
    op.create_index("ix_memory_states_due", "memory_states", ["due_at"])


def downgrade() -> None:
    op.drop_index("ix_memory_states_due", table_name="memory_states")
    op.drop_index("ix_memory_states_user_id", table_name="memory_states")
    op.drop_table("memory_states")
    op.drop_index("ix_review_sessions_user_completed", table_name="review_sessions")
    op.drop_index("ix_review_sessions_user_id", table_name="review_sessions")
    op.drop_table("review_sessions")
