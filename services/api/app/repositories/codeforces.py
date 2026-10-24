"""Data access for Codeforces sync. Every read/write is owner-scoped by user_id
(except shared `problems`), so authorization is enforced in the data layer."""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import String, cast, func, select, update
from sqlalchemy.orm import Session

from app.models import CfAccount, Problem, Submission, SyncJob, User, UserProblem
from app.models.base import utcnow

ACTIVE_JOB_STATUSES = ("pending", "running")


def create_account(db: Session, *, user_id: uuid.UUID, handle: str) -> CfAccount:
    account = CfAccount(user_id=user_id, handle=handle, handle_lower=handle.lower())
    db.add(account)
    db.commit()
    return account


def find_account_by_handle(db: Session, handle: str) -> CfAccount | None:
    return db.scalar(select(CfAccount).where(CfAccount.handle_lower == handle.lower()))


def get_account(db: Session, *, user_id: uuid.UUID, account_id: uuid.UUID) -> CfAccount | None:
    return db.scalar(
        select(CfAccount).where(CfAccount.id == account_id, CfAccount.user_id == user_id)
    )


def list_accounts(db: Session, user_id: uuid.UUID) -> Sequence[CfAccount]:
    return db.scalars(
        select(CfAccount).where(CfAccount.user_id == user_id).order_by(CfAccount.created_at)
    ).all()


def lock_account(db: Session, account: CfAccount) -> None:
    """Serialize syncs per account. FOR UPDATE is honored by PostgreSQL and
    safely ignored by the SQLite dialect (single-connection tests)."""
    db.execute(
        select(CfAccount.id).where(CfAccount.id == account.id).with_for_update()
    )


def get_active_job(db: Session, account_id: uuid.UUID) -> SyncJob | None:
    return db.scalar(
        select(SyncJob)
        .where(SyncJob.cf_account_id == account_id, SyncJob.status.in_(ACTIVE_JOB_STATUSES))
        .order_by(SyncJob.created_at.desc())
    )


def other_running_job(
    db: Session, account_id: uuid.UUID, exclude_job_id: uuid.UUID
) -> SyncJob | None:
    return db.scalar(
        select(SyncJob).where(
            SyncJob.cf_account_id == account_id,
            SyncJob.status == "running",
            SyncJob.id != exclude_job_id,
        )
    )


def create_job(db: Session, *, account_id: uuid.UUID, job_type: str) -> SyncJob:
    job = SyncJob(cf_account_id=account_id, job_type=job_type)
    db.add(job)
    db.commit()
    return job


def claim_job(db: Session, job_id: uuid.UUID) -> bool:
    """Atomic pending→running transition; False means another delivery claimed it."""
    result = db.execute(
        update(SyncJob)
        .where(SyncJob.id == job_id, SyncJob.status == "pending")
        .values(status="running", started_at=utcnow(), attempt_count=SyncJob.attempt_count + 1)
    )
    db.commit()
    return result.rowcount == 1


def finish_job(
    db: Session,
    job_id: uuid.UUID,
    *,
    status: str,
    error_summary: str | None = None,
    progress: dict | None = None,
) -> None:
    values = {"status": status, "completed_at": utcnow(), "updated_at": utcnow()}
    if error_summary is not None:
        values["error_summary"] = error_summary[:2000]
    if progress is not None:
        values["progress"] = progress
    db.execute(update(SyncJob).where(SyncJob.id == job_id).values(**values))
    db.commit()


def update_job_progress(db: Session, job_id: uuid.UUID, progress: dict) -> None:
    db.execute(
        update(SyncJob)
        .where(SyncJob.id == job_id)
        .values(progress=progress, updated_at=utcnow())
    )
    db.commit()


def latest_jobs(db: Session, account_id: uuid.UUID, limit: int = 5) -> Sequence[SyncJob]:
    return db.scalars(
        select(SyncJob)
        .where(SyncJob.cf_account_id == account_id)
        .order_by(SyncJob.created_at.desc())
        .limit(limit)
    ).all()


def upsert_problems(db: Session, problem_dicts: list[dict]) -> dict[str, Problem]:
    """Idempotent upsert of shared problem metadata keyed by canonical_key."""
    keys = [p["canonical_key"] for p in problem_dicts]
    existing = {
        p.canonical_key: p
        for p in db.scalars(select(Problem).where(Problem.canonical_key.in_(keys))).all()
    }
    for data in problem_dicts:
        key = data["canonical_key"]
        row = existing.get(key)
        if row is None:
            row = Problem(**data)
            db.add(row)
            existing[key] = row
        else:
            # Identity never changes; descriptive fields refresh.
            row.name = data["name"]
            row.rating = data["rating"]
            row.tags = data["tags"]
            row.url = data["url"] or row.url
    db.flush()
    return existing


def upsert_submissions(
    db: Session,
    *,
    account_id: uuid.UUID,
    problems: dict[str, Problem],
    submission_dicts: list[dict],
) -> int:
    """Insert new submissions, refresh mutable fields of existing ones.

    Returns the number of newly inserted rows. Idempotent: re-processing the
    same payload inserts nothing.
    """
    ids = [s["cf_submission_id"] for s in submission_dicts]
    existing_rows = {
        row.cf_submission_id: row
        for row in db.scalars(
            select(Submission).where(
                Submission.cf_account_id == account_id,
                Submission.cf_submission_id.in_(ids),
            )
        ).all()
    }
    new_count = 0
    for data in submission_dicts:
        problem = problems[data.pop("canonical_key")]
        row = existing_rows.get(data["cf_submission_id"])
        if row is None:
            db.add(Submission(cf_account_id=account_id, problem_id=problem.id, **data))
            new_count += 1
        else:
            # Verdict and counts may refresh (e.g. TESTING -> OK on re-sync);
            # submitted_at is immutable — source creation time is the truth.
            row.verdict = data["verdict"]
            row.passed_test_count = data["passed_test_count"]
            row.time_consumed_millis = data["time_consumed_millis"]
            row.memory_consumed_bytes = data["memory_consumed_bytes"]
    db.flush()
    return new_count


def recompute_user_problems(
    db: Session, *, user_id: uuid.UUID, problem_ids: list[uuid.UUID]
) -> None:
    """Derive per-user solve rollups from accepted submissions.

    first_solved_at can only move EARLIER (min semantics): a later import,
    resubmission, or revision must never overwrite the original first solve.
    """
    if not problem_ids:
        return
    rows = db.execute(
        select(
            Submission.problem_id,
            func.min(Submission.submitted_at),
            func.max(Submission.submitted_at),
        )
        .join(CfAccount, Submission.cf_account_id == CfAccount.id)
        .where(
            CfAccount.user_id == user_id,
            Submission.verdict == "OK",
            Submission.problem_id.in_(problem_ids),
        )
        .group_by(Submission.problem_id)
    ).all()

    for problem_id, first_at, last_at in rows:
        rollup = db.scalar(
            select(UserProblem).where(
                UserProblem.user_id == user_id, UserProblem.problem_id == problem_id
            )
        )
        if rollup is None:
            db.add(
                UserProblem(
                    user_id=user_id,
                    problem_id=problem_id,
                    first_solved_at=first_at,
                    last_solved_at=last_at,
                    accepted_count=1,
                )
            )
        else:
            rollup.first_solved_at = min(rollup.first_solved_at, first_at)
            rollup.last_solved_at = max(rollup.last_solved_at, last_at)
    db.flush()

    # accepted_count per problem (all accepted submissions for this user).
    counts = db.execute(
        select(Submission.problem_id, func.count())
        .join(CfAccount, Submission.cf_account_id == CfAccount.id)
        .where(
            CfAccount.user_id == user_id,
            Submission.verdict == "OK",
            Submission.problem_id.in_(problem_ids),
        )
        .group_by(Submission.problem_id)
    ).all()
    for problem_id, count in counts:
        rollup = db.scalar(
            select(UserProblem).where(
                UserProblem.user_id == user_id, UserProblem.problem_id == problem_id
            )
        )
        if rollup is not None:
            rollup.accepted_count = count
    db.flush()


def account_totals(db: Session, account: CfAccount) -> dict[str, int]:
    submissions = db.scalar(
        select(func.count()).select_from(Submission).where(Submission.cf_account_id == account.id)
    )
    solved = db.scalar(
        select(func.count()).select_from(UserProblem).where(UserProblem.user_id == account.user_id)
    )
    return {"submissions": int(submissions or 0), "solved_problems": int(solved or 0)}


SORTABLE_PROBLEM_FIELDS = ("first_solved_at", "last_solved_at", "name", "rating", "accepted_count")


def _problem_order(sort: str, order: str) -> list:
    """Deterministic ordering: primary column plus stable tiebreakers.
    Nullable ratings always sort last in both directions."""
    descending = order == "desc"
    if sort == "rating":
        col = Problem.rating.desc() if descending else Problem.rating.asc()
        rating = col.nulls_last()
        return [rating, Problem.name.asc()]
    primary = {
        "first_solved_at": UserProblem.first_solved_at,
        "last_solved_at": UserProblem.last_solved_at,
        "name": Problem.name,
        "accepted_count": UserProblem.accepted_count,
    }[sort]
    tiebreak = UserProblem.first_solved_at if sort == "name" else Problem.name
    return [
        primary.desc() if descending else primary.asc(),
        tiebreak.asc(),
    ]


def solved_problems_page(
    db: Session,
    *,
    user_id: uuid.UUID,
    page: int,
    page_size: int,
    search: str | None = None,
    rating_min: int | None = None,
    rating_max: int | None = None,
    tag: str | None = None,
    sort: str = "first_solved_at",
    order: str = "desc",
) -> tuple[list[dict], int]:
    """Solved-problem rows (problem joined with the user's rollup), filtered
    and sorted server-side. `sort`/`order` must already be validated."""
    conditions = [UserProblem.user_id == user_id]

    if search:
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append(Problem.name.ilike(f"%{escaped}%", escape="\\"))
    if rating_min is not None:
        conditions.append(Problem.rating >= rating_min)
    if rating_max is not None:
        conditions.append(Problem.rating <= rating_max)
    if tag:
        # Quote-wrapped containment on the JSON text: '"two"' never matches
        # 'two-pointers'. Portable across SQLite (CAST to TEXT) and PG (JSONB
        # to text); tag filters are scans either way (no GIN index yet).
        conditions.append(cast(Problem.tags, String).ilike(f'%"{tag}"%'))

    total = db.scalar(
        select(func.count())
        .select_from(UserProblem)
        .join(Problem, UserProblem.problem_id == Problem.id)
        .where(*conditions)
    )
    rows = db.execute(
        select(UserProblem, Problem)
        .join(Problem, UserProblem.problem_id == Problem.id)
        .where(*conditions)
        .order_by(*_problem_order(sort, order))
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [
        {
            "id": problem.id,
            "canonical_key": problem.canonical_key,
            "contest_id": problem.contest_id,
            "problem_index": problem.problem_index,
            "name": problem.name,
            "rating": problem.rating,
            "tags": problem.tags,
            "url": problem.url,
            "first_solved_at": rollup.first_solved_at,
            "last_solved_at": rollup.last_solved_at,
            "accepted_count": rollup.accepted_count,
        }
        for rollup, problem in rows
    ]
    return items, int(total or 0)


def get_user(db: Session, user_id: uuid.UUID) -> User | None:
    return db.get(User, user_id)


def stale_running_jobs(db: Session, *, older_than: datetime) -> list[SyncJob]:
    cutoff = older_than
    return list(
        db.scalars(
            select(SyncJob).where(
                SyncJob.status == "running", SyncJob.updated_at < cutoff
            )
        ).all()
    )


def utc_now() -> datetime:
    return datetime.now(UTC)
