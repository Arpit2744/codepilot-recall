"""Dashboard aggregate queries — derived from canonical records on read.

Per ADR-0005 there is no materialized daily_activity table: activity counts
are computed from `submissions` / `user_problems` (both protected by unique
constraints), so repeated syncs can never inflate them and timezone changes
need no invalidation.
"""

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CfAccount, Problem, Submission, UserProblem


def submission_timestamps(
    db: Session, *, user_id: uuid.UUID, start_utc: datetime, end_utc: datetime
) -> Sequence[datetime]:
    """Source submission times in [start, end) across the user's accounts."""
    return db.execute(
        select(Submission.submitted_at)
        .join(CfAccount, Submission.cf_account_id == CfAccount.id)
        .where(
            CfAccount.user_id == user_id,
            Submission.submitted_at >= start_utc,
            Submission.submitted_at < end_utc,
        )
        .order_by(Submission.submitted_at)
    ).scalars().all()


def first_solve_timestamps(
    db: Session, *, user_id: uuid.UUID, start_utc: datetime, end_utc: datetime
) -> Sequence[datetime]:
    """Distinct first-solve times in [start, end)."""
    return db.execute(
        select(UserProblem.first_solved_at)
        .where(
            UserProblem.user_id == user_id,
            UserProblem.first_solved_at >= start_utc,
            UserProblem.first_solved_at < end_utc,
        )
        .order_by(UserProblem.first_solved_at)
    ).scalars().all()


def totals(db: Session, user_id: uuid.UUID) -> dict[str, int]:
    submissions = db.scalar(
        select(func.count())
        .select_from(Submission)
        .join(CfAccount, Submission.cf_account_id == CfAccount.id)
        .where(CfAccount.user_id == user_id)
    )
    solved = db.scalar(
        select(func.count()).select_from(UserProblem).where(UserProblem.user_id == user_id)
    )
    return {"submissions": int(submissions or 0), "solved_problems": int(solved or 0)}


def recent_first_solves(
    db: Session, *, user_id: uuid.UUID, limit: int = 5
) -> Sequence[dict]:
    """Most recently first-solved problems (newest discovery date first)."""
    rows = db.execute(
        select(UserProblem, Problem)
        .join(Problem, UserProblem.problem_id == Problem.id)
        .where(UserProblem.user_id == user_id)
        .order_by(UserProblem.first_solved_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "problem_id": problem.id,
            "name": problem.name,
            "contest_id": problem.contest_id,
            "problem_index": problem.problem_index,
            "rating": problem.rating,
            "first_solved_at": rollup.first_solved_at,
        }
        for rollup, problem in rows
    ]


def account_statuses(db: Session, user_id: uuid.UUID) -> Sequence[CfAccount]:
    return db.scalars(
        select(CfAccount).where(CfAccount.user_id == user_id).order_by(CfAccount.created_at)
    ).all()
