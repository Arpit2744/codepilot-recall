"""activity aggregation indexes (Phase 2)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-24
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Dashboard time-range scans: per-account submission windows.
    op.create_index(
        "ix_submissions_account_submitted",
        "submissions",
        ["cf_account_id", "submitted_at"],
    )
    # First-solve recency scans per user (summary/heatmap/table ordering).
    op.create_index(
        "ix_user_problems_user_first_solved",
        "user_problems",
        ["user_id", "first_solved_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_problems_user_first_solved", table_name="user_problems")
    op.drop_index("ix_submissions_account_submitted", table_name="submissions")
