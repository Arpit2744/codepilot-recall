"""Review lifecycle schemas. Outcome policy documented in docs/api.md."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ReviewOutcome = Literal["again", "hard", "good", "easy"]
HelpLevel = Literal["none", "hint", "editorial"]


class StartReviewRequest(BaseModel):
    problem_id: uuid.UUID


class CompleteReviewRequest(BaseModel):
    outcome: ReviewOutcome
    independent: bool | None = None
    help_level: HelpLevel | None = None
    duration_seconds: int | None = Field(default=None, ge=0, le=86_400)
    notes: str | None = Field(default=None, max_length=2000)


class ProblemRef(BaseModel):
    id: uuid.UUID
    name: str
    contest_id: int | None
    problem_index: str | None
    rating: int | None
    tags: list[str]
    url: str | None


class ReviewSessionOut(BaseModel):
    id: uuid.UUID
    problem_id: uuid.UUID
    status: str
    started_at: datetime
    completed_at: datetime | None
    outcome: str | None
    independent: bool | None
    help_level: str | None
    duration_seconds: int | None
    notes: str | None


class MemoryStateOut(BaseModel):
    due_at: datetime
    last_review_at: datetime | None
    stability: float | None
    difficulty: float | None
    repetitions: int
    lapses: int
    scheduler_version: str


class ReviewSessionResponse(BaseModel):
    session: ReviewSessionOut
    problem: ProblemRef
    memory: MemoryStateOut | None


class CompleteReviewResponse(BaseModel):
    session: ReviewSessionOut
    problem: ProblemRef
    memory: MemoryStateOut


class DueItemOut(BaseModel):
    problem: ProblemRef
    due_at: datetime
    last_review_at: datetime | None
    repetitions: int
    lapses: int
    stability: float | None
    # "due" (arrived) or "overdue" (past the policy grace window).
    status: Literal["due", "overdue"]
    overdue_seconds: int
    # 1=Critical (>=30d overdue) 2=High (>=7d) 3=Overdue 4=Due. Urgency
    # ranking only — computed by the queue layer, never stored, never part
    # of FSRS scheduling.
    priority_tier: int
    priority_reason: str
    # FSRS MODEL ESTIMATE of recall probability, or null when no valid
    # history exists. Distinct from observed recall (review outcomes).
    retrievability: float | None
    risk: Literal["high", "elevated", "low"] | None


class UpcomingItemOut(BaseModel):
    problem: ProblemRef
    due_at: datetime
    last_review_at: datetime | None
    repetitions: int
    lapses: int
    stability: float | None
    status: Literal["upcoming"]
    seconds_until_due: int
    priority_tier: None = None
    priority_reason: str
    retrievability: float | None = None
    risk: None = None


class DueListResponse(BaseModel):
    mode: Literal["due", "upcoming"]
    items: list[DueItemOut] | list[UpcomingItemOut]


class HistoryItemOut(BaseModel):
    id: uuid.UUID
    problem_id: uuid.UUID
    problem_name: str
    outcome: str
    independent: bool | None
    help_level: str | None
    duration_seconds: int | None
    started_at: datetime
    completed_at: datetime


class HistoryResponse(BaseModel):
    items: list[HistoryItemOut]
    total: int
    page: int
    page_size: int
