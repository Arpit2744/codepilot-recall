"""Enqueue sync work onto the Celery worker.

The API never performs Codeforces network calls itself — it persists a
pending `sync_jobs` row and asks the worker to execute it. If the broker is
unreachable the row simply stays pending: the periodic dispatcher re-enqueues
pending jobs once the broker returns, so nothing is lost.
"""

import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)

SYNC_TASK_NAME = "worker.codeforces.sync_account"


def enqueue_sync(account_id, job_id) -> bool:
    """Send the sync task; returns False when the broker is unavailable."""
    settings = get_settings()
    if not settings.redis_url:
        logger.info("no redis configured; job %s stays pending for the dispatcher", job_id)
        return False
    try:
        from celery import Celery  # imported lazily: optional for API-only tests

        app = Celery(__name__, broker=settings.redis_url)
        app.send_task(SYNC_TASK_NAME, args=[str(account_id), str(job_id)])
        return True
    except Exception as exc:  # noqa: BLE001 — broker outages must not fail requests
        logger.warning("enqueue failed for job %s: %s", job_id, exc)
        return False
