"""Verify a restored backup: schema version + representative row integrity.

Usage: python scripts/verify_backup.py  (DATABASE_URL selects the restored DB)
"""

import os
from datetime import UTC

from sqlalchemy import create_engine, text

from scripts.seed_demo import (
    ACCOUNT_ID,
    DUE,
    PROBLEM_ID,
    T0,
    USER_ID,
)

EXPECTED_TABLES = {
    "users",
    "cf_accounts",
    "problems",
    "submissions",
    "user_problems",
    "sync_jobs",
    "review_sessions",
    "memory_states",
    "user_sessions",
    "alembic_version",
}


def main() -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert version == "0005", f"unexpected schema version {version!r}"

        rows = conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        )
        tables = set(rows.scalars())
        assert EXPECTED_TABLES <= tables, f"missing tables: {EXPECTED_TABLES - tables}"

        email, pw_hash = conn.execute(
            text("SELECT email, password_hash FROM users WHERE id = :id"), {"id": str(USER_ID)}
        ).one()
        assert email == "seed@example.com"
        assert pw_hash.startswith("$argon2id$"), "password hash must survive restore"

        handle = conn.execute(
            text("SELECT handle FROM cf_accounts WHERE id = :id"), {"id": str(ACCOUNT_ID)}
        ).scalar()
        assert handle == "seed-handle"

        rating, tags = conn.execute(
            text("SELECT rating, tags::text FROM problems WHERE id = :id"),
            {"id": str(PROBLEM_ID)},
        ).one()
        assert rating == 1500 and "math" in tags

        first_solved = conn.execute(
            text("SELECT first_solved_at FROM user_problems WHERE user_id = :u"),
            {"u": str(USER_ID)},
        ).scalar()
        assert first_solved.replace(tzinfo=UTC) == T0, "first-solve timestamp must be exact"

        due_at, stability = conn.execute(
            text("SELECT due_at, stability FROM memory_states WHERE user_id = :u"),
            {"u": str(USER_ID)},
        ).one()
        assert due_at.replace(tzinfo=UTC) == DUE and abs(stability - 2.3065) < 1e-6

        counts = {
            table: conn.execute(text(f"SELECT count(*) FROM {table}")).scalar()
            for table in ("submissions", "review_sessions", "sync_jobs")
        }
        assert counts == {"submissions": 1, "review_sessions": 1, "sync_jobs": 1}, counts

    print("verify OK: schema 0005, all representative rows intact")


if __name__ == "__main__":
    main()
