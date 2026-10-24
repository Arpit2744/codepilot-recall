"""Solved-problem endpoints: filtered, sorted, paginated, owner-scoped."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id
from app.core.db import get_db
from app.repositories.codeforces import SORTABLE_PROBLEM_FIELDS, solved_problems_page
from app.schemas.codeforces import ProblemListResponse

router = APIRouter(prefix="/problems", tags=["problems"])

SORT_OPTIONS = ", ".join(SORTABLE_PROBLEM_FIELDS)


@router.get("", response_model=ProblemListResponse)
def list_solved_problems(
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    search: Annotated[str | None, Query(min_length=1, max_length=100)] = None,
    rating_min: Annotated[int | None, Query(ge=0, le=10000)] = None,
    rating_max: Annotated[int | None, Query(ge=0, le=10000)] = None,
    tag: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    sort: Annotated[str, Query(max_length=32)] = "first_solved_at",
    order: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
):
    if sort not in SORTABLE_PROBLEM_FIELDS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported sort {sort!r}; expected one of: {SORT_OPTIONS}",
        )
    if rating_min is not None and rating_max is not None and rating_min > rating_max:
        raise HTTPException(status_code=422, detail="rating_min must not exceed rating_max")

    items, total = solved_problems_page(
        db,
        user_id=user_id,
        page=page,
        page_size=page_size,
        search=search,
        rating_min=rating_min,
        rating_max=rating_max,
        tag=tag,
        sort=sort,
        order=order,
    )
    return ProblemListResponse(items=items, total=total, page=page, page_size=page_size)
