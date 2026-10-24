"""Review lifecycle endpoints: start a session, complete it, list due/history."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id, require_csrf, validate_browser_origin
from app.core.db import get_db
from app.models import MemoryState, Problem, ReviewSession, UserProblem
from app.repositories import reviews as repo
from app.schemas.reviews import (
    CompleteReviewRequest,
    CompleteReviewResponse,
    DueListResponse,
    HistoryItemOut,
    HistoryResponse,
    MemoryStateOut,
    ProblemRef,
    ReviewSessionOut,
    ReviewSessionResponse,
    StartReviewRequest,
)
from app.services import reviews as service

router = APIRouter(prefix="/reviews", tags=["reviews"])


def _problem_ref(problem: Problem) -> ProblemRef:
    return ProblemRef(
        id=problem.id,
        name=problem.name,
        contest_id=problem.contest_id,
        problem_index=problem.problem_index,
        rating=problem.rating,
        tags=problem.tags,
        url=problem.url,
    )


def _session_out(review: ReviewSession, problem_id: uuid.UUID) -> ReviewSessionOut:
    return ReviewSessionOut(
        id=review.id,
        problem_id=problem_id,
        status=review.status,
        started_at=review.started_at,
        completed_at=review.completed_at,
        outcome=review.outcome,
        independent=review.independent,
        help_level=review.help_level,
        duration_seconds=review.duration_seconds,
        notes=review.notes,
    )


def _memory_out(memory: MemoryState | None) -> MemoryStateOut | None:
    if memory is None:
        return None
    return MemoryStateOut(
        due_at=memory.due_at,
        last_review_at=memory.last_review_at,
        stability=memory.stability,
        difficulty=memory.difficulty,
        repetitions=memory.repetitions,
        lapses=memory.lapses,
        scheduler_version=memory.scheduler_version,
    )


def _load_context(
    db: Session, review: ReviewSession
) -> tuple[Problem, uuid.UUID, MemoryState | None]:
    rollup = db.get(UserProblem, review.user_problem_id)
    problem = db.get(Problem, rollup.problem_id) if rollup else None
    if problem is None:  # defensive: FK cascade keeps these consistent
        raise HTTPException(status_code=404, detail="Problem no longer exists")
    return problem, rollup.problem_id, repo.get_memory(db, review.user_problem_id)


@router.post("/sessions", response_model=ReviewSessionResponse, status_code=201)
def start_review(
    payload: StartReviewRequest,
    request: Request,
    user_id: Annotated[uuid.UUID, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
):
    validate_browser_origin(request)
    try:
        review = service.start_review(db, user_id=user_id, problem_id=payload.problem_id)
    except service.ProblemNotSolved:
        raise HTTPException(
            status_code=404,
            detail="Problem not found among your solved problems",
        ) from None
    problem, problem_id, memory = _load_context(db, review)
    return ReviewSessionResponse(
        session=_session_out(review, problem_id),
        problem=_problem_ref(problem),
        memory=_memory_out(memory),
    )


@router.get("/sessions/{session_id}", response_model=ReviewSessionResponse)
def get_review_session(
    session_id: uuid.UUID,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    review = repo.get_session(db, user_id=user_id, session_id=session_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Review session not found")
    problem, problem_id, memory = _load_context(db, review)
    return ReviewSessionResponse(
        session=_session_out(review, problem_id),
        problem=_problem_ref(problem),
        memory=_memory_out(memory),
    )


@router.post("/sessions/{session_id}/complete", response_model=CompleteReviewResponse)
def complete_review_session(
    session_id: uuid.UUID,
    payload: CompleteReviewRequest,
    request: Request,
    user_id: Annotated[uuid.UUID, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
):
    validate_browser_origin(request)
    try:
        review, memory = service.complete_review(
            db,
            user_id=user_id,
            session_id=session_id,
            outcome=payload.outcome,
            independent=payload.independent,
            help_level=payload.help_level,
            duration_seconds=payload.duration_seconds,
            notes=payload.notes,
        )
    except service.SessionNotFound:
        raise HTTPException(status_code=404, detail="Review session not found") from None
    except service.SessionAlreadyCompleted:
        raise HTTPException(
            status_code=409,
            detail="Review session is already completed; the scheduler was not advanced again",
        ) from None
    except service.MemoryStateInvalid as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Stored memory state is corrupt; the review was NOT recorded. {exc}",
        ) from exc

    problem, problem_id, _ = _load_context(db, review)
    return CompleteReviewResponse(
        session=_session_out(review, problem_id),
        problem=_problem_ref(problem),
        memory=_memory_out(memory),
    )


@router.get("/due", response_model=DueListResponse)
def list_due(
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    mode: Annotated[str, Query(pattern="^(due|upcoming)$")] = "due",
):
    """Revision queue. mode=due (default): due_at <= now, urgency-ranked.
    mode=upcoming: future items only, clearly typed — never mixed into due.

    Ranking and risk labels are computed by the queue layer from persisted
    facts; FSRS due dates and serialized state are authoritative and never
    rewritten here.
    """
    from app.integrations.fsrs import adapter
    from app.models.base import utcnow
    from app.services import queue as queue_service

    now = utcnow()
    rows = repo.queue_items(db, user_id=user_id, now=now, mode=mode, limit=limit)

    enriched: list[dict] = []
    for row in rows:
        row = dict(row)
        estimate_unavailable = False
        try:
            row["retrievability"] = adapter.retrievability(
                row["scheduler_state"], at=now
            )
        except adapter.MemoryStateCorrupt:
            # Read path: represent invalid data explicitly, never invent an
            # estimate and never hide the item (its due date is still fact).
            row["retrievability"] = None
            estimate_unavailable = True
        row.pop("scheduler_state", None)

        if mode == "due":
            classified = queue_service.classify_due(row, now=now)
            if estimate_unavailable:
                classified["priority_reason"] += (
                    " — recall estimate unavailable (stored state unreadable)"
                )
            row.update(classified)
            enriched.append(row)
        else:
            row.update(queue_service.classify_upcoming(row, now=now))
            enriched.append(row)

    ordered = (
        queue_service.order_due_queue(enriched)
        if mode == "due"
        else queue_service.order_upcoming_queue(enriched)
    )
    return DueListResponse(mode=mode, items=ordered)


@router.get("/history", response_model=HistoryResponse)
def review_history(
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    items, total = repo.history_page(db, user_id=user_id, page=page, page_size=page_size)
    return HistoryResponse(
        items=[HistoryItemOut(**item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )
