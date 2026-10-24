"""Review-session lifecycle: start → complete, with atomic FSRS updates.

Invariants (ADR-0006):
- Completion is idempotent: the pending→completed transition happens under a
  row lock; a second completion observes `completed` and raises
  SessionAlreadyCompleted without touching the scheduler.
- The review record and the memory-state update commit in ONE transaction;
  any failure rolls both back.
- The Codeforces acceptance never initializes an FSRS review — the first
  explicit outcome does.
- independent_solve_verified is set only on an independent Good/Easy review.
"""

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from app.integrations.fsrs import adapter
from app.models import ReviewSession, UserProblem
from app.models.base import utcnow
from app.repositories import reviews as repo


class ProblemNotSolved(Exception):
    """The user has no solved-problem record for this problem."""


class SessionNotFound(Exception):
    """No such review session for this user (unknown or another user's)."""


class SessionAlreadyCompleted(Exception):
    """The session was already completed; FSRS must not advance twice."""


class MemoryStateInvalid(Exception):
    """Stored scheduler state is corrupt; manual intervention required."""


def start_review(db: Session, *, user_id: uuid.UUID, problem_id: uuid.UUID) -> ReviewSession:
    rollup = repo.get_solved_user_problem(db, user_id=user_id, problem_id=problem_id)
    if rollup is None:
        raise ProblemNotSolved(str(problem_id))
    return repo.create_session(db, user_id=user_id, user_problem_id=rollup.id, started_at=utcnow())


def complete_review(
    db: Session,
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    outcome: str,
    independent: bool | None,
    help_level: str | None,
    duration_seconds: int | None,
    notes: str | None,
    now: datetime | None = None,
) -> tuple[ReviewSession, object]:
    now = now or utcnow()
    review_session = repo.get_session(db, user_id=user_id, session_id=session_id)
    if review_session is None:
        raise SessionNotFound(str(session_id))

    repo.lock_session(db, review_session)
    db.refresh(review_session)
    if review_session.status == "completed":
        raise SessionAlreadyCompleted(str(session_id))

    memory = repo.get_memory(db, review_session.user_problem_id)

    try:
        new_state = adapter.apply_review(
            memory.scheduler_state if memory is not None else None,
            outcome,
            now=now,
            duration_seconds=duration_seconds,
        )
    except adapter.MemoryStateCorrupt as exc:
        db.rollback()
        raise MemoryStateInvalid(str(exc)) from exc

    view = adapter.card_view(new_state)

    review_session.status = "completed"
    review_session.completed_at = now
    review_session.outcome = outcome
    review_session.independent = independent
    review_session.help_level = help_level
    review_session.duration_seconds = duration_seconds
    review_session.notes = notes

    memory_row = repo.upsert_memory(
        db,
        user_id=user_id,
        user_problem_id=review_session.user_problem_id,
        scheduler_state=new_state,
        scheduler_version=adapter.SCHEDULER_VERSION,
        due_at=view["due_at"],
        last_review_at=view["last_review_at"],
        stability=view["stability"],
        difficulty=view["difficulty"],
        previous_repetitions=memory.repetitions if memory else 0,
        previous_lapses=memory.lapses if memory else 0,
        lapse_now=outcome == "again",
    )

    if outcome in ("good", "easy") and independent is True:
        rollup = db.get(UserProblem, review_session.user_problem_id)
        if rollup is not None:
            rollup.independent_solve_verified = True

    db.commit()  # review record + memory state + verified flag: one transaction
    db.refresh(review_session)
    return review_session, memory_row
