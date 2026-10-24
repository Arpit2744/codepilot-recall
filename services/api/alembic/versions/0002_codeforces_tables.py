"""codeforces integration tables (Phase 1)

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-24
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON = sa.JSON().with_variant(JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "cf_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("handle", sa.String(length=24), nullable=False),
        sa.Column("handle_lower", sa.String(length=24), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sync_cursor", _JSON, nullable=True),
        sa.Column("last_sync_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE", name="fk_cf_accounts_user_id"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_cf_accounts"),
        sa.UniqueConstraint("handle_lower", name="uq_cf_accounts_handle_lower"),
    )
    op.create_index("ix_cf_accounts_user_id", "cf_accounts", ["user_id"])

    op.create_table(
        "problems",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("canonical_key", sa.String(length=128), nullable=False),
        sa.Column("contest_id", sa.Integer(), nullable=True),
        sa.Column("problem_index", sa.String(length=8), nullable=True),
        sa.Column("problemset_name", sa.String(length=128), nullable=True),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("tags", _JSON, nullable=False),
        sa.Column("url", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_problems"),
        sa.UniqueConstraint("canonical_key", name="uq_problems_canonical_key"),
    )

    op.create_table(
        "submissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("cf_account_id", sa.Uuid(), nullable=False),
        sa.Column("cf_submission_id", sa.BigInteger(), nullable=False),
        sa.Column("problem_id", sa.Uuid(), nullable=False),
        sa.Column("verdict", sa.String(length=32), nullable=True),
        sa.Column("programming_language", sa.String(length=64), nullable=True),
        sa.Column("passed_test_count", sa.Integer(), nullable=True),
        sa.Column("time_consumed_millis", sa.Integer(), nullable=True),
        sa.Column("memory_consumed_bytes", sa.BigInteger(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_meta", _JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["cf_account_id"],
            ["cf_accounts.id"],
            ondelete="CASCADE",
            name="fk_submissions_cf_account_id",
        ),
        sa.ForeignKeyConstraint(
            ["problem_id"], ["problems.id"], ondelete="RESTRICT", name="fk_submissions_problem_id"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_submissions"),
        sa.UniqueConstraint(
            "cf_account_id", "cf_submission_id", name="uq_submissions_account_source_id"
        ),
    )
    op.create_index(
        "ix_submissions_problem_submitted", "submissions", ["problem_id", "submitted_at"]
    )

    op.create_table(
        "user_problems",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("problem_id", sa.Uuid(), nullable=False),
        sa.Column("first_solved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_solved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_count", sa.Integer(), nullable=False),
        sa.Column("first_solve_source", sa.String(length=32), nullable=False),
        sa.Column("independent_solve_verified", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE", name="fk_user_problems_user_id"
        ),
        sa.ForeignKeyConstraint(
            ["problem_id"], ["problems.id"], ondelete="RESTRICT", name="fk_user_problems_problem_id"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_problems"),
        sa.UniqueConstraint("user_id", "problem_id", name="uq_user_problems_user_problem"),
    )
    op.create_index("ix_user_problems_user_id", "user_problems", ["user_id"])

    op.create_table(
        "sync_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("cf_account_id", sa.Uuid(), nullable=False),
        sa.Column("job_type", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("progress", _JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["cf_account_id"],
            ["cf_accounts.id"],
            ondelete="CASCADE",
            name="fk_sync_jobs_cf_account_id",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sync_jobs"),
    )
    op.create_index("ix_sync_jobs_account_created", "sync_jobs", ["cf_account_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_sync_jobs_account_created", table_name="sync_jobs")
    op.drop_table("sync_jobs")
    op.drop_index("ix_user_problems_user_id", table_name="user_problems")
    op.drop_table("user_problems")
    op.drop_index("ix_submissions_problem_submitted", table_name="submissions")
    op.drop_table("submissions")
    op.drop_table("problems")
    op.drop_index("ix_cf_accounts_user_id", table_name="cf_accounts")
    op.drop_table("cf_accounts")
