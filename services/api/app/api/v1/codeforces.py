"""Codeforces account endpoints: link handles, trigger syncs, report status."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_id, require_csrf, validate_browser_origin
from app.core.config import get_settings
from app.core.db import get_db
from app.repositories import codeforces as repo
from app.schemas.codeforces import (
    AccountCreatedResponse,
    AccountOut,
    CreateAccountRequest,
    JobOut,
    SyncStatusResponse,
    SyncTotals,
    SyncTriggerResponse,
)
from app.services.sync.queue import enqueue_sync

router = APIRouter(prefix="/codeforces", tags=["codeforces"])


def _account_out(account) -> AccountOut:
    return AccountOut(
        id=account.id,
        handle=account.handle,
        verified_at=account.verified_at,
        last_synced_at=account.last_synced_at,
        last_sync_error=account.last_sync_error,
        created_at=account.created_at,
    )


def _job_out(job) -> JobOut:
    return JobOut(
        id=job.id,
        job_type=job.job_type,
        status=job.status,
        attempt_count=job.attempt_count,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error_summary=job.error_summary,
        progress=job.progress,
        created_at=job.created_at,
    )


def _owned_account(db: Session, user_id: uuid.UUID, account_id: uuid.UUID):
    account = repo.get_account(db, user_id=user_id, account_id=account_id)
    if account is None:
        # 404 rather than 403: do not leak the existence of other users' accounts.
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.post("/accounts", response_model=AccountCreatedResponse, status_code=202)
def create_account(
    payload: CreateAccountRequest,
    request: Request,
    user_id: Annotated[uuid.UUID, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
):
    """Link a public Codeforces handle and queue the historical import.

    Handles are public data: any user may track the same handle (ADR-0009)
    — a public username alone proves nothing about ownership, so linking
    grants read-only tracking, never an exclusive claim. The handle is
    validated against user.info by the worker; failures surface in sync
    status. We never request Codeforces credentials.
    """
    validate_browser_origin(request)
    settings = get_settings()
    if len(repo.list_accounts(db, user_id)) >= settings.max_linked_accounts:
        raise HTTPException(
            status_code=422,
            detail=f"Account limit reached (max {settings.max_linked_accounts} linked handles)",
        )

    # Conflict only when THIS user already tracks the handle.
    existing = repo.get_account_by_handle(db, user_id=user_id, handle=payload.handle)
    if existing is not None:
        raise HTTPException(status_code=409, detail="You have already linked this handle")

    try:
        account = repo.create_account(db, user_id=user_id, handle=payload.handle)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="You have already linked this handle") from None

    job = repo.create_job(db, account_id=account.id, job_type="historical")
    queued = enqueue_sync(account.id, job.id)
    return AccountCreatedResponse(
        account=_account_out(account), job=_job_out(job), queued=queued
    )


@router.get("/accounts", response_model=list[AccountOut])
def list_accounts(
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    return [_account_out(a) for a in repo.list_accounts(db, user_id)]


@router.post("/accounts/{account_id}/sync", response_model=SyncTriggerResponse, status_code=202)
def trigger_sync(
    account_id: uuid.UUID,
    request: Request,
    user_id: Annotated[uuid.UUID, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
):
    """Queue an incremental sync; returns the active job if one exists."""
    validate_browser_origin(request)
    account = _owned_account(db, user_id, account_id)

    active = repo.get_active_job(db, account.id)
    if active is not None:
        return SyncTriggerResponse(
            account=_account_out(account),
            job=_job_out(active),
            queued=True,
            already_active=True,
        )

    job = repo.create_job(db, account_id=account.id, job_type="incremental")
    queued = enqueue_sync(account.id, job.id)
    return SyncTriggerResponse(
        account=_account_out(account), job=_job_out(job), queued=queued
    )


@router.get("/accounts/{account_id}/sync-status", response_model=SyncStatusResponse)
def sync_status(
    account_id: uuid.UUID,
    user_id: Annotated[uuid.UUID, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
):
    account = _owned_account(db, user_id, account_id)
    totals = repo.account_totals(db, account)
    jobs = repo.latest_jobs(db, account.id, limit=5)
    return SyncStatusResponse(
        account=_account_out(account),
        latest_jobs=[_job_out(j) for j in jobs],
        totals=SyncTotals(**totals),
    )
