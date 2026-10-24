"""Liveness tasks used by monitoring and the Docker healthcheck."""

from worker import __version__
from worker.celery_app import celery_app


@celery_app.task(name="worker.health.ping")
def ping() -> dict[str, str]:
    return {"status": "ok", "worker_version": __version__}
