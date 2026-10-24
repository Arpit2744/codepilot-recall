"""Celery application instance shared by worker and beat processes."""

from celery import Celery
from celery.schedules import schedule as celery_schedule

from worker.config import get_settings

settings = get_settings()

celery_app = Celery(
    "codepilot",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "worker.tasks.health",
        "worker.tasks.codeforces",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    task_default_queue="default",
    result_expires=3600,
    worker_prefetch_multiplier=1,  # sync jobs are long; don't hoard tasks
    task_acks_late=True,           # requeue on worker crash
    beat_schedule={
        "dispatch-codeforces-syncs": {
            "task": "worker.codeforces.dispatch_scheduled_syncs",
            "schedule": celery_schedule(float(settings.cf_sync_interval_minutes * 60)),
        }
    },
)
