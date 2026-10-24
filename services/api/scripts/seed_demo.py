"""Seed deterministic demo data for the backup/restore rehearsal.

Usage: python scripts/seed_demo.py  (DATABASE_URL selects the target)

Not wired into the application; a CI rehearsal tool only. Creates one user
with password, one active session, one Codeforces account/problem/
submission/user_problem, and one completed review with its memory state —
enough to verify representative row integrity after a restore.
"""

import os
import uuid
from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import (
    CfAccount,
    MemoryState,
    Problem,
    ReviewSession,
    Submission,
    SyncJob,
    User,
    UserProblem,
)

# Fixed identifiers so verify_backup.py can assert exact rows.
USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
ACCOUNT_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
PROBLEM_ID = uuid.UUID("00000000-0000-0000-0000-000000000003")
SESSION_TOKEN_HASH = "ab" * 32  # sha256-hex shape; not a real token

T0 = datetime(2026, 1, 15, 10, 0, tzinfo=UTC)
DUE = datetime(2026, 2, 15, 10, 0, tzinfo=UTC)


def main() -> None:
    engine = create_engine(os.environ["DATABASE_URL"])
    db = sessionmaker(bind=engine, expire_on_commit=False)()

    user = User(
        id=USER_ID,
        email="seed@example.com",
        display_name="Seed",
        password_hash="$argon2id$v=19$m=65536,t=2,p=4$c2VlZHNlZWRzZWVkc2VlZA$"
        "c2VlZHB3c2VlZHB3c2VlZHB3c2VlZHB3c2VlZHB3c2VlZHA",
    )
    db.add(user)
    db.add(
        CfAccount(
            id=ACCOUNT_ID,
            user_id=USER_ID,
            handle="seed-handle",
            handle_lower="seed-handle",
            last_synced_at=T0,
            sync_cursor={"last_seen_submission_id": 1001},
        )
    )
    db.add(
        Problem(
            id=PROBLEM_ID,
            canonical_key="100-A",
            contest_id=100,
            problem_index="A",
            name="Seed Problem",
            rating=1500,
            tags=["math"],
        )
    )
    db.add(
        Submission(
            cf_account_id=ACCOUNT_ID,
            cf_submission_id=1001,
            problem_id=PROBLEM_ID,
            verdict="OK",
            submitted_at=T0,
        )
    )
    db.add(
        UserProblem(
            user_id=USER_ID,
            problem_id=PROBLEM_ID,
            first_solved_at=T0,
            last_solved_at=T0,
            accepted_count=1,
        )
    )
    db.add(
        SyncJob(
            cf_account_id=ACCOUNT_ID,
            job_type="historical",
            status="succeeded",
            attempt_count=1,
            started_at=T0,
            completed_at=T0,
        )
    )
    review = ReviewSession(
        user_id=USER_ID,
        user_problem_id=db.query(UserProblem).filter_by(user_id=USER_ID).one().id,
        started_at=T0,
        completed_at=T0,
        status="completed",
        outcome="good",
        independent=True,
        help_level="none",
    )
    db.add(review)
    db.flush()
    db.add(
        MemoryState(
            user_id=USER_ID,
            user_problem_id=review.user_problem_id,
            scheduler_state={
                "version": "fsrs-6.3.2",
                "scheduler": {},
                "card": {"stability": 2.3065},
            },
            scheduler_version="fsrs-6.3.2",
            due_at=DUE,
            last_review_at=T0,
            stability=2.3065,
            difficulty=2.118103970459016,
            repetitions=1,
            lapses=0,
        )
    )
    db.commit()
    print("seeded: user/account/problem/submission/user_problem/job/review/memory")


if __name__ == "__main__":
    main()
