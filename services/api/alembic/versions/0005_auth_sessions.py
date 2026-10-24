"""auth sessions and shared-handle policy (Phase 5)

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-25
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_token_hash", sa.String(length=64), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_via", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE", name="fk_user_sessions_user_id"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_sessions"),
        sa.UniqueConstraint("token_hash", name="uq_user_sessions_token_hash"),
    )
    op.create_index("ix_user_sessions_user", "user_sessions", ["user_id", "revoked_at"])
    op.create_index("ix_user_sessions_expiry", "user_sessions", ["expires_at"])

    # Codeforces handles are public data — move from one-global-owner to
    # per-user uniqueness so multiple users can track the same handle
    # (ADR-0009). batch_alter_table keeps this portable: plain ALTERs on
    # PostgreSQL, table-rebuild on SQLite.
    with op.batch_alter_table("cf_accounts") as batch:
        batch.drop_constraint("uq_cf_accounts_handle_lower", type_="unique")
        batch.create_unique_constraint(
            "uq_cf_accounts_user_handle", ["user_id", "handle_lower"]
        )


def downgrade() -> None:
    with op.batch_alter_table("cf_accounts") as batch:
        batch.drop_constraint("uq_cf_accounts_user_handle", type_="unique")
        batch.create_unique_constraint("uq_cf_accounts_handle_lower", ["handle_lower"])
    op.drop_index("ix_user_sessions_expiry", table_name="user_sessions")
    op.drop_index("ix_user_sessions_user", table_name="user_sessions")
    op.drop_table("user_sessions")
