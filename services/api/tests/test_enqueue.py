"""Regression tests for the Phase 6 production enqueue failure.

The API image installs only this package's dependencies; enqueue_sync()
lazy-imports Celery, which was missing there — production logged
"No module named 'celery'" and every initial sync stayed pending. These
tests pin the dependency declaration and the enqueue behavior (task name,
IDs, TLS for rediss:// brokers) with fakes only — no broker, no database.
"""

import importlib.util
import ssl
import uuid
from pathlib import Path

from app.core.config import get_settings
from app.core.redis_tls import redis_ssl_options
from app.services.sync import queue

SERVICE_DIR = Path(__file__).resolve().parents[1]


def test_api_package_declares_pinned_celery():
    """The API image installs only this pyproject — celery must be declared
    here, not just in the worker, or production cannot enqueue."""
    pyproject = (SERVICE_DIR / "pyproject.toml").read_text(encoding="utf-8")
    assert '"celery==5.6.3"' in pyproject


def test_celery_importable_in_api_environment():
    assert importlib.util.find_spec("celery") is not None


class FakeConf(dict):
    """Mimics Celery's config mapping: attribute-style writes, item reads."""

    def __setattr__(self, key, value):
        self[key] = value


class FakeCeleryApp:
    """Records constructor args and send_task calls; never connects."""

    instances: list["FakeCeleryApp"] = []

    def __init__(self, name, broker=None, **kwargs):
        self.name = name
        self.broker = broker
        self.conf = FakeConf()
        self.sent: list[tuple[str, list]] = []
        FakeCeleryApp.instances.append(self)

    def send_task(self, name, args=None, **kwargs):
        self.sent.append((name, args))


def _fresh_queue(monkeypatch, redis_url: str):
    monkeypatch.setenv("REDIS_URL", redis_url)
    get_settings.cache_clear()
    FakeCeleryApp.instances.clear()
    monkeypatch.setattr("celery.Celery", FakeCeleryApp)


def test_enqueue_sync_sends_expected_task_with_tls_broker(monkeypatch):
    _fresh_queue(monkeypatch, "rediss://default:secret@host.upstash.io:6379")
    account_id, job_id = uuid.uuid4(), uuid.uuid4()

    queued = queue.enqueue_sync(account_id, job_id)

    assert queued is True
    assert len(FakeCeleryApp.instances) == 1
    app = FakeCeleryApp.instances[0]
    assert app.broker == "rediss://default:secret@host.upstash.io:6379"
    # TLS-only brokers must get certificate verification.
    assert app.conf["broker_use_ssl"] == {"ssl_cert_reqs": ssl.CERT_REQUIRED}
    assert app.sent == [
        ("worker.codeforces.sync_account", [str(account_id), str(job_id)])
    ]


def test_enqueue_sync_plain_redis_broker_has_no_tls_options(monkeypatch):
    _fresh_queue(monkeypatch, "redis://localhost:6379/0")
    account_id, job_id = uuid.uuid4(), uuid.uuid4()

    assert queue.enqueue_sync(account_id, job_id) is True

    app = FakeCeleryApp.instances[0]
    assert app.broker == "redis://localhost:6379/0"
    assert "broker_use_ssl" not in app.conf


def test_enqueue_sync_without_redis_stays_pending(monkeypatch):
    _fresh_queue(monkeypatch, "")
    # No FakeCelery patching needed: the short-circuit must not import Celery.
    assert queue.enqueue_sync(uuid.uuid4(), uuid.uuid4()) is False
    assert FakeCeleryApp.instances == []


def test_redis_tls_helper_still_requires_verification():
    assert redis_ssl_options("rediss://x") == {"ssl_cert_reqs": ssl.CERT_REQUIRED}
