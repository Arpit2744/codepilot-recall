"""Request/response schemas for the Codeforces endpoints."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CreateAccountRequest(BaseModel):
    handle: str = Field(min_length=1, max_length=24, pattern=r"^[A-Za-z0-9_.-]+$")


class JobOut(BaseModel):
    id: uuid.UUID
    job_type: str
    status: str
    attempt_count: int
    started_at: datetime | None
    completed_at: datetime | None
    error_summary: str | None
    progress: dict[str, Any] | None
    created_at: datetime


class AccountOut(BaseModel):
    id: uuid.UUID
    handle: str
    verified_at: datetime | None
    last_synced_at: datetime | None
    last_sync_error: str | None
    created_at: datetime


class AccountCreatedResponse(BaseModel):
    account: AccountOut
    job: JobOut
    queued: bool


class SyncTriggerResponse(BaseModel):
    account: AccountOut
    job: JobOut
    queued: bool
    already_active: bool = False


class SyncTotals(BaseModel):
    submissions: int
    solved_problems: int


class SyncStatusResponse(BaseModel):
    account: AccountOut
    latest_jobs: list[JobOut]
    totals: SyncTotals


class SolvedProblemOut(BaseModel):
    id: uuid.UUID
    canonical_key: str
    contest_id: int | None
    problem_index: str | None
    name: str
    rating: int | None
    tags: list[str]
    url: str | None
    first_solved_at: datetime
    last_solved_at: datetime
    accepted_count: int


class ProblemListResponse(BaseModel):
    items: list[SolvedProblemOut]
    total: int
    page: int
    page_size: int
