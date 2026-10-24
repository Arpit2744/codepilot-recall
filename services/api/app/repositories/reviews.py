"""Review-session and memory-state data access. Owner-scoped like all repos."""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import MemoryState, Problem, ReviewSession, UserProblem


def get_solved_user_problem(
    db: Session, *, user_id: uuid.UUID, problem_id: uuid.UUID
) -> UserProblem | None:
    """The user's rollup row for a solved problem, if it exists."""
    return db.scalar(
        select(UserProblem).where(
            UserProblem.user_id == user_id, UserProblem.problem_id == problem_id
        )
    )


def create_session(
    db: Session, *, user_id: uuid.UUID, user_problem_id: uuid.UUID, started_at: datetime
) -> ReviewSession:
    session = ReviewSession(
        user_id=user_id, user_problem_id=user_problem_id, started_at=started_at
    )
    db.add(session)
    db.commit()
    return session


def get_session(
    db: Session, *, user_id: uuid.UUID, session_id: uuid.UUID
) -> ReviewSession | None:
    return db.scalar(
        select(ReviewSession).where(
            ReviewSession.id == session_id, ReviewSession.user_id == user_id
        )
    )


def lock_session(db: Session, review_session: ReviewSession) -> None:
    """Serialize concurrent completions of the same session.

    FOR UPDATE is honored by PostgreSQL; the SQLite dialect ignores it
    (tests run on a single connection, so behavior is equivalent).
    """
    db.execute(
        select(ReviewSession.id).where(ReviewSession.id == review_session.id).with_for_update()
    )


def get_memory(db: Session, user_problem_id: uuid.UUID) -> MemoryState | None:
    return db.scalar(
        select(MemoryState).where(MemoryState.user_problem_id == user_problem_id)
    )


def upsert_memory(
    db: Session,
    *,
    user_id: uuid.UUID,
    user_problem_id: uuid.UUID,
    scheduler_state: dict,
    scheduler_version: str,
    due_at: datetime,
    last_review_at: datetime | None,
    stability: float | None,
    difficulty: float | None,
    previous_repetitions: int,
    previous_lapses: int,
    lapse_now: bool,
) -> MemoryState:
    memory = get_memory(db, user_problem_id)
    if memory is None:
        memory = MemoryState(
            user_id=user_id,
            user_problem_id=user_problem_id,
            scheduler_state=scheduler_state,
            scheduler_version=scheduler_version,
            due_at=due_at,
            last_review_at=last_review_at,
            stability=stability,
            difficulty=difficulty,
            repetitions=previous_repetitions + 1,
            lapses=previous_lapses + (1 if lapse_now else 0),
        )
        db.add(memory)
    else:
        memory.scheduler_state = scheduler_state
        memory.scheduler_version = scheduler_version
        memory.due_at = due_at
        memory.last_review_at = last_review_at
        memory.stability = stability
        memory.difficulty = difficulty
        memory.repetitions = previous_repetitions + 1
        memory.lapses = previous_lapses + (1 if lapse_now else 0)
    db.flush()
    return memory


def queue_items(
    db: Session,
    *,
    user_id: uuid.UUID,
    now: datetime,
    mode: str,
    limit: int = 50,
) -> Sequence[dict]:
    """Raw queue rows for the urgency layer.

    mode="due": due_at <= now. mode="upcoming": due_at > now (soonest first).
    Includes the serialized scheduler state so estimates can be computed
    without touching stored rows; bounded by `limit`.
    """
    condition = (
        MemoryState.due_at <= now if mode == "due" else MemoryState.due_at > now
    )
    rows = db.execute(
        select(MemoryState, UserProblem, Problem)
        .join(UserProblem, MemoryState.user_problem_id == UserProblem.id)
        .join(Problem, UserProblem.problem_id == Problem.id)
        .where(MemoryState.user_id == user_id, condition)
        .order_by(MemoryState.due_at.asc())
        .limit(limit)
    ).all()
    return [
        {
            "problem": {
                "id": problem.id,
                "name": problem.name,
                "contest_id": problem.contest_id,
                "problem_index": problem.problem_index,
                "rating": problem.rating,
                "tags": problem.tags,
                "url": problem.url,
            },
            "canonical_key": problem.canonical_key,
            "due_at": memory.due_at,
            "last_review_at": memory.last_review_at,
            "repetitions": memory.repetitions,
            "lapses": memory.lapses,
            "stability": memory.stability,
            "scheduler_state": memory.scheduler_state,
        }
        for memory, _rollup, problem in rows
    ]


def completed_review_timestamps(
    db: Session, *, user_id: uuid.UUID, start_utc: datetime, end_utc: datetime
) -> Sequence[datetime]:
    """Completion times of finished reviews in [start, end) — the only source
    of review activity (started-but-unfinished sessions never count)."""
    return db.execute(
        select(ReviewSession.completed_at)
        .where(
            ReviewSession.user_id == user_id,
            ReviewSession.status == "completed",
            ReviewSession.completed_at.is_not(None),
            ReviewSession.completed_at >= start_utc,
            ReviewSession.completed_at < end_utc,
        )
        .order_by(ReviewSession.completed_at)
    ).scalars().all()


def history_page(
    db: Session, *, user_id: uuid.UUID, page: int, page_size: int
) -> tuple[list[dict], int]:
    total = db.scalar(
        select(func.count())
        .select_from(ReviewSession)
        .where(ReviewSession.user_id == user_id, ReviewSession.status == "completed")
    )
    rows = db.execute(
        select(ReviewSession, Problem)
        .join(UserProblem, ReviewSession.user_problem_id == UserProblem.id)
        .join(Problem, UserProblem.problem_id == Problem.id)
        .where(
            ReviewSession.user_id == user_id, ReviewSession.status == "completed"
        )
        .order_by(ReviewSession.completed_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [
        {
            "id": review.id,
            "problem_id": problem.id,
            "problem_name": problem.name,
            "outcome": review.outcome,
            "independent": review.independent,
            "help_level": review.help_level,
            "duration_seconds": review.duration_seconds,
            "started_at": review.started_at,
            "completed_at": review.completed_at,
        }
        for review, problem in rows
    ]
    return items, int(total or 0)
