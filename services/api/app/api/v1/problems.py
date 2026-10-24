"""Solved-problem summary endpoints (minimal Phase 1 surface)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id
from app.core.db import get_db
from app.repositories.codeforces import solved_problems_page
from app.schemas.codeforces import ProblemListResponse

router = APIRouter(prefix="/problems", tags=["problems"])


@router.get("", response_model=ProblemListResponse)
def list_solved_problems(
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    if page > 1_000_000:
        raise HTTPException(status_code=422, detail="page out of range")
    items, total = solved_problems_page(db, user_id=user_id, page=page, page_size=page_size)
    return ProblemListResponse(items=items, total=total, page=page, page_size=page_size)
