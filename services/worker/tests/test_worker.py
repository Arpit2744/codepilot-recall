"""Worker configuration and task execution tests."""

from worker import __version__
from worker.celery_app import celery_app
from worker.config import WorkerSettings
from worker.tasks.health import ping


def test_ping_task_executes_eagerly(eager_celery):
    result = ping.delay()
    assert result.get() == {"status": "ok", "worker_version": __version__}


def test_celery_app_configuration():
    conf = celery_app.conf
    assert conf.task_serializer == "json"
    assert conf.accept_content == ["json"]
    assert conf.timezone == "UTC"
    assert conf.enable_utc is True
    assert conf.task_acks_late is True
    # Long sync jobs must not be hoarded by an idle worker.
    assert conf.worker_prefetch_multiplier == 1


def test_settings_read_environment(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://cache:6379/2")
    settings = WorkerSettings()
    assert settings.redis_url == "redis://cache:6379/2"
    assert settings.cf_sync_interval_minutes == 30
