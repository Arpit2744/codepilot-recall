"""Dashboard endpoints: summary aggregates and timezone-correct heatmap."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id
from app.core.db import get_db
from app.models.base import utcnow
from app.repositories import dashboard as dash_repo
from app.schemas.dashboard import (
    AccountSyncStatus,
    DashboardSummaryResponse,
    DashboardTotals,
    HeatmapDay,
    HeatmapResponse,
    RecentFirstSolve,
)
from app.services.dashboard import (
    MAX_HEATMAP_DAYS,
    bucket_by_local_date,
    build_continuous_days,
    compute_streak,
    local_range_to_utc,
    resolve_timezone,
    streak_window_utc,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

HEATMAP_MODES = ("submissions", "first_solves", "reviews")

REVIEWS_UNAVAILABLE = (
    "Review sessions are tracked from Phase 3; no review data exists yet, "
    "so this mode is intentionally unavailable rather than shown as zero."
)


def _resolve_tz_or_422(name: str):
    try:
        return resolve_timezone(name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/summary", response_model=DashboardSummaryResponse)
def dashboard_summary(
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
    timezone: Annotated[str, Query(max_length=64)] = "UTC",
):
    tz = _resolve_tz_or_422(timezone)
    today_local = utcnow().astimezone(tz).date()

    totals = dash_repo.totals(db, user_id)

    streak_start, streak_end = streak_window_utc(today_local, tz)
    submission_days = bucket_by_local_date(
        dash_repo.submission_timestamps(
            db, user_id=user_id, start_utc=streak_start, end_utc=streak_end
        ),
        tz,
    )
    first_solve_days = bucket_by_local_date(
        dash_repo.first_solve_timestamps(
            db, user_id=user_id, start_utc=streak_start, end_utc=streak_end
        ),
        tz,
    )
    active_dates = set(submission_days) | set(first_solve_days)

    accounts = dash_repo.account_statuses(db, user_id)
    return DashboardSummaryResponse(
        timezone=str(tz),
        generated_at=utcnow(),
        totals=DashboardTotals(**totals),
        current_streak_days=compute_streak(active_dates, today_local),
        recent_first_solves=[
            RecentFirstSolve(**row) for row in dash_repo.recent_first_solves(db, user_id=user_id)
        ],
        accounts=[
            AccountSyncStatus(
                id=a.id,
                handle=a.handle,
                last_synced_at=a.last_synced_at,
                last_sync_error=a.last_sync_error,
            )
            for a in accounts
        ],
    )


@router.get("/heatmap", response_model=HeatmapResponse)
def dashboard_heatmap(
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
    from_: Annotated[date, Query(alias="from")],
    to: Annotated[date, Query()],
    timezone: Annotated[str, Query(max_length=64)] = "UTC",
    mode: Annotated[str, Query(max_length=32)] = "submissions",
):
    tz = _resolve_tz_or_422(timezone)
    if mode not in HEATMAP_MODES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported mode {mode!r}; expected one of {HEATMAP_MODES}",
        )
    if from_ > to:
        raise HTTPException(status_code=422, detail="'from' must not be after 'to'")
    if (to - from_).days > MAX_HEATMAP_DAYS:
        raise HTTPException(status_code=422, detail=f"Range exceeds {MAX_HEATMAP_DAYS} days")

    if mode == "reviews":
        # Honest unavailability: never fabricate zero-activity review data.
        return HeatmapResponse(
            timezone=str(tz),
            mode="reviews",
            from_date=from_.isoformat(),
            to_date=to.isoformat(),
            available=False,
            days=[],
            max_count=0,
            message=REVIEWS_UNAVAILABLE,
        )

    start_utc, end_utc = local_range_to_utc(from_, to, tz)
    if mode == "submissions":
        timestamps = dash_repo.submission_timestamps(
            db, user_id=user_id, start_utc=start_utc, end_utc=end_utc
        )
    else:
        timestamps = dash_repo.first_solve_timestamps(
            db, user_id=user_id, start_utc=start_utc, end_utc=end_utc
        )

    counts = bucket_by_local_date(timestamps, tz)
    days = build_continuous_days(counts, from_, to)
    return HeatmapResponse(
        timezone=str(tz),
        mode=mode,
        from_date=from_.isoformat(),
        to_date=to.isoformat(),
        available=True,
        days=[HeatmapDay(**d) for d in days],
        max_count=max((d["count"] for d in days), default=0),
    )
