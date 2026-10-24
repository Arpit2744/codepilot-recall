"""Worker test fixtures: eager mode so no broker is needed."""

import pytest

from worker.celery_app import celery_app


@pytest.fixture
def eager_celery(monkeypatch):
    monkeypatch.setattr(celery_app.conf, "task_always_eager", True)
    monkeypatch.setattr(celery_app.conf, "task_eager_propagates", True)
    yield celery_app
