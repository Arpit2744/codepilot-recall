"""Dashboard request/response schemas."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

HeatmapMode = Literal["submissions", "first_solves", "reviews"]


class DashboardTotals(BaseModel):
    submissions: int
    solved_problems: int


class RecentFirstSolve(BaseModel):
    problem_id: uuid.UUID
    name: str
    contest_id: int | None
    problem_index: str | None
    rating: int | None
    first_solved_at: datetime


class AccountSyncStatus(BaseModel):
    id: uuid.UUID
    handle: str
    last_synced_at: datetime | None
    last_sync_error: str | None


class DashboardSummaryResponse(BaseModel):
    timezone: str
    generated_at: datetime
    totals: DashboardTotals
    current_streak_days: int
    recent_first_solves: list[RecentFirstSolve]
    accounts: list[AccountSyncStatus]


class HeatmapDay(BaseModel):
    date: str  # local calendar date, YYYY-MM-DD
    count: int


class HeatmapResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    timezone: str
    mode: HeatmapMode
    from_date: str = Field(alias="from")
    to_date: str = Field(alias="to")
    available: bool
    # Populated only when available; empty list otherwise.
    days: list[HeatmapDay]
    max_count: int
    # Set when a mode exists in the product but its data does not (reviews → Phase 3).
    message: str | None = None
