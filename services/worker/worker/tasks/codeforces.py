"""Codeforces synchronization tasks.

The worker is the only process that talks to the Codeforces API: one shared
rate limiter, one retry policy. Job rows are claimed atomically so duplicate
task deliveries (acks-late redeliveries) are safe, and per-account locking in
the importer prevents concurrent syncs of the same account.
"""

import logging
import random
import uuid
from datetime import UTC, timedelta

from app.core import db as app_db
from app.core.config import get_settings as get_api_settings
from app.integrations.codeforces.client import (
    CfApiError,
    CfHandleNotFound,
    CfTransientError,
    CodeforcesApiClient,
)
from app.integrations.codeforces.rate_limiter import build_rate_limiter
from app.models import CfAccount, SyncJob
from app.models.base import utcnow
from app.repositories import codeforces as repo
from app.services.sync.importer import SyncImporter
from app.services.sync.queue import SYNC_TASK_NAME
from celery.exceptions import Retry
from sqlalchemy import select
from sqlalchemy import update as sa_update

from worker.celery_app import celery_app

logger = logging.getLogger(__name__)

RETRY_BASE_SECONDS = 30.0
RETRY_MAX_SECONDS = 900.0


def make_client(settings) -> CodeforcesApiClient:
    limiter = build_rate_limiter(settings.redis_url, settings.cf_request_interval_seconds)
    return CodeforcesApiClient(settings=settings, rate_limiter=limiter)


def _retry_countdown(retries: int) -> float:
    return min(RETRY_BASE_SECONDS * (2**retries) + random.uniform(0, 10), RETRY_MAX_SECONDS)


@celery_app.task(name="worker.codeforces.sync_account", bind=True, acks_late=True)
def sync_account(self, account_id: str, job_id: str) -> dict:
    settings = get_api_settings()
    try:
        account_uuid = uuid.UUID(account_id)
        job_uuid = uuid.UUID(job_id)
    except ValueError:
        logger.error("sync_account received malformed ids: %s %s", account_id, job_id)
        return {"status": "rejected", "reason": "malformed ids"}

    with app_db.SessionLocal() as db:
        job = db.get(SyncJob, job_uuid)
        if job is None or job.cf_account_id != account_uuid:
            logger.warning("sync_account job %s not found or mismatched", job_id)
            return {"status": "rejected", "reason": "unknown job"}
        if job.status in ("succeeded", "failed", "cancelled"):
            # Terminal already (e.g. duplicate delivery): nothing to do.
            return {"status": "skipped", "reason": f"job already {job.status}"}
        if job.status == "pending" and not repo.claim_job(db, job_uuid):
            # Another delivery already claimed it — duplicate delivery is safe.
            return {"status": "skipped", "reason": "already claimed"}
        db.refresh(job)
        account = db.get(CfAccount, account_uuid)
        if account is None:
            repo.finish_job(db, job_uuid, status="failed", error_summary="account missing")
            return {"status": "failed", "reason": "account missing"}

        importer = SyncImporter(
            db,
            account,
            make_client(settings),
            page_size=settings.cf_status_page_size,
            historical_max_pages=settings.cf_historical_max_pages,
            incremental_max_pages=settings.cf_incremental_max_pages,
        )
        try:
            stats = importer.run(job)
        except CfTransientError as exc:
            # Transient upstream failure: hand the job back to pending so the
            # scheduled Celery retry can re-claim it, then retry with backoff.
            db.execute(
                sa_update(SyncJob)
                .where(SyncJob.id == job_uuid)
                .values(status="pending", completed_at=None, updated_at=utcnow())
            )
            db.commit()
            countdown = _retry_countdown(self.request.retries)
            logger.warning(
                "transient sync failure job=%s retry in %.0fs: %s", job_id, countdown, exc
            )
            try:
                raise self.retry(exc=exc, countdown=countdown) from exc
            except Retry:
                raise  # normal path: Celery will call us again
            except Exception:
                # Retries exhausted — record the permanent failure.
                repo.finish_job(
                    db, job_uuid, status="failed", error_summary=f"retries exhausted: {exc}"
                )
                return {"status": "failed", "job_id": job_id, "reason": "retries exhausted"}
        except (CfHandleNotFound, CfApiError) as exc:
            # Permanent failure: the importer already recorded it on the job.
            return {"status": "failed_permanent", "job_id": job_id, "reason": str(exc)[:300]}

        return {"status": "ok", "job_id": job_id, **stats.as_progress()}


@celery_app.task(name="worker.codeforces.dispatch_scheduled_syncs")
def dispatch_scheduled_syncs() -> dict:
    """Periodic dispatcher: recover stale jobs, enqueue pending, schedule due syncs."""
    settings = get_api_settings()
    interval = timedelta(minutes=settings.cf_sync_interval_minutes)
    stale_cutoff = utcnow() - max(interval * 2, timedelta(hours=1))

    enqueued_pending = 0
    scheduled = 0
    recovered_stale = 0

    with app_db.SessionLocal() as db:
        # 1) Jobs stuck `running` far beyond any healthy sync: the worker died.
        for job in repo.stale_running_jobs(db, older_than=stale_cutoff):
            repo.finish_job(
                db, job.id, status="failed", error_summary="stale running job recovered"
            )
            recovered_stale += 1

        # 2) Pending jobs that never reached a worker (broker outage at request time).
        for job in db.scalars(select(SyncJob).where(SyncJob.status == "pending")).all():
            celery_app.send_task(SYNC_TASK_NAME, args=[str(job.cf_account_id), str(job.id)])
            enqueued_pending += 1

        # 3) Incremental syncs for accounts due under the configured interval.
        now = utcnow()
        for account in db.scalars(select(CfAccount)).all():
            if repo.get_active_job(db, account.id) is not None:
                continue
            last = account.last_synced_at
            if last is not None and last.tzinfo is None:
                # SQLite test storage loses tzinfo; PostgreSQL preserves it.
                last = last.replace(tzinfo=UTC)
            due = last is None or (now - last) >= interval
            if not due:
                continue
            job = repo.create_job(db, account_id=account.id, job_type="incremental")
            celery_app.send_task(SYNC_TASK_NAME, args=[str(account.id), str(job.id)])
            scheduled += 1

    summary = {
        "recovered_stale": recovered_stale,
        "enqueued_pending": enqueued_pending,
        "scheduled": scheduled,
    }
    logger.info("dispatch_scheduled_syncs: %s", summary)
    return summary
