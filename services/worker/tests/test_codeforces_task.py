"""Worker sync-task tests: eager execution against an in-memory database.

No broker and no network: SessionLocal is pointed at SQLite and the Codeforces
client is replaced with a fake.
"""

from datetime import UTC, datetime, timedelta

import pytest
from app.core import db as app_db
from app.integrations.codeforces.client import CfHandleNotFound, CfTransientError
from app.models import Base, CfAccount, SyncJob, User, UserProblem
from app.repositories import codeforces as repo
from celery.exceptions import Retry
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from worker.tasks import codeforces as cf_tasks

T0 = datetime(2024, 5, 1, 12, 0, tzinfo=UTC)


def cf_problem(contest=1, index="A"):
    return {"contestId": contest, "index": index, "name": f"Problem {index}", "tags": ["math"]}


def cf_item(sub_id, ts, verdict):
    return {
        "id": sub_id,
        "creationTimeSeconds": int(ts.timestamp()),
        "problem": cf_problem(),
        "author": {"members": [], "participationType": "PRACTICE"},
        "verdict": verdict,
    }


class FakeClient:
    def __init__(self, pages, info_error=None):
        self.pages = pages
        self.info_error = info_error
        self.fetches = 0

    def get_user_info(self, handle):
        if self.info_error is not None:
            raise self.info_error
        return {"handle": handle}

    def fetch_status_page(self, handle, from_, count):
        self.fetches += 1
        page_index = (from_ - 1) // count
        return self.pages[page_index] if page_index < len(self.pages) else []


@pytest.fixture
def sqlite_session_factory(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    # Route the shared SessionLocal at our test database.
    monkeypatch.setattr(app_db, "SessionLocal", factory)
    return factory


@pytest.fixture
def account_job(sqlite_session_factory):
    with sqlite_session_factory() as db:
        user = User(email="w@example.com", display_name="w")
        db.add(user)
        db.commit()
        account = repo.create_account(db, user_id=user.id, handle="tourist")
        job = repo.create_job(db, account_id=account.id, job_type="historical")
        return account.id, job.id


def use_fake_client(monkeypatch, client):
    monkeypatch.setattr(cf_tasks, "make_client", lambda settings: client)


def test_sync_success_updates_job_and_cursor(
    eager_celery, sqlite_session_factory, account_job, monkeypatch
):
    account_id, job_id = account_job
    use_fake_client(monkeypatch, FakeClient([[cf_item(1, T0, "OK")]]))

    result = cf_tasks.sync_account.delay(str(account_id), str(job_id)).get()

    assert result["status"] == "ok"
    with sqlite_session_factory() as db:
        job = db.get(SyncJob, job_id)
        account = db.get(CfAccount, account_id)
        assert job.status == "succeeded"
        assert job.attempt_count == 1
        assert account.sync_cursor == {"last_seen_submission_id": 1}
        assert account.last_sync_error is None
        assert db.query(UserProblem).count() == 1


def test_duplicate_delivery_skips_claimed_job(
    eager_celery, sqlite_session_factory, account_job, monkeypatch
):
    account_id, job_id = account_job
    use_fake_client(monkeypatch, FakeClient([[cf_item(1, T0, "OK")]]))

    first = cf_tasks.sync_account.delay(str(account_id), str(job_id)).get()
    assert first["status"] == "ok"

    second = cf_tasks.sync_account.delay(str(account_id), str(job_id)).get()
    assert second["status"] in ("skipped", "rejected", "ok")

    with sqlite_session_factory() as db:
        job = db.get(SyncJob, job_id)
        assert job.status == "succeeded"
        assert job.attempt_count == 1  # never re-claimed


def test_permanent_handle_not_found_fails_job_without_retry(
    eager_celery, sqlite_session_factory, account_job, monkeypatch
):
    account_id, job_id = account_job
    use_fake_client(
        monkeypatch,
        FakeClient([], info_error=CfHandleNotFound("handles: some handles not found")),
    )

    result = cf_tasks.sync_account.delay(str(account_id), str(job_id)).get()

    assert result["status"] == "failed_permanent"
    with sqlite_session_factory() as db:
        job = db.get(SyncJob, job_id)
        account = db.get(CfAccount, account_id)
        assert job.status == "failed"
        assert "not found" in job.error_summary
        assert account.last_synced_at is None
        assert "not found" in account.last_sync_error


def test_transient_failure_resets_job_pending_for_retry(
    sqlite_session_factory, account_job, monkeypatch
):
    account_id, job_id = account_job
    use_fake_client(
        monkeypatch,
        FakeClient([], info_error=CfTransientError("CF down after 3 attempts")),
    )

    def fake_retry(exc=None, countdown=None, **kwargs):
        raise Retry(when=countdown, exc=exc)

    monkeypatch.setattr(cf_tasks.sync_account, "retry", fake_retry, raising=False)

    with pytest.raises(Retry) as info:
        # Call the task instance directly; `self.retry` is our fake.
        cf_tasks.sync_account(str(account_id), str(job_id))

    assert 0 < info.value.when <= cf_tasks.RETRY_MAX_SECONDS
    with sqlite_session_factory() as db:
        job = db.get(SyncJob, job_id)
        # Handed back to pending so the scheduled retry can re-claim it.
        assert job.status == "pending"
        assert "CF down" in job.error_summary


def test_dispatch_enqueues_pending_and_due_incremental(
    eager_celery, sqlite_session_factory, monkeypatch
):
    sent = []

    def record_send(name, args=None, **kwargs):
        sent.append((name, args))

    monkeypatch.setattr(cf_tasks.celery_app, "send_task", record_send)

    with sqlite_session_factory() as db:
        user = User(email="d@example.com", display_name="d")
        db.add(user)
        db.commit()
        # Never-synced account holding a pending historical job: the pending
        # job gets (re)enqueued, and NO extra incremental must be scheduled.
        account = repo.create_account(db, user_id=user.id, handle="due-user")
        pending = repo.create_job(db, account_id=account.id, job_type="historical")

        # A recently-synced account with no jobs must NOT get a new job.
        fresh = repo.create_account(db, user_id=user.id, handle="fresh-user")
        fresh.last_synced_at = datetime.now(UTC)

        # An account synced long ago with no jobs IS due for an incremental.
        due = repo.create_account(db, user_id=user.id, handle="overdue-user")
        due.last_synced_at = datetime.now(UTC) - timedelta(hours=3)
        db.commit()
        due_id = due.id

    summary = cf_tasks.dispatch_scheduled_syncs.delay().get()

    assert summary["enqueued_pending"] == 1
    assert summary["scheduled"] == 1
    assert (cf_tasks.SYNC_TASK_NAME, [str(account.id), str(pending.id)]) in sent

    with sqlite_session_factory() as db:
        # The due account got exactly one new incremental job, dispatched.
        active = repo.get_active_job(db, due_id)
        assert active is not None and active.job_type == "incremental"
        assert (cf_tasks.SYNC_TASK_NAME, [str(due_id), str(active.id)]) in sent
        # The fresh account was skipped entirely.
        fresh_jobs = db.query(SyncJob).filter(SyncJob.cf_account_id == fresh.id).all()
        assert fresh_jobs == []


def test_dispatch_recovers_stale_running_jobs(eager_celery, sqlite_session_factory, monkeypatch):
    monkeypatch.setattr(cf_tasks.celery_app, "send_task", lambda name, args=None, **kw: None)

    with sqlite_session_factory() as db:
        user = User(email="s@example.com", display_name="s")
        db.add(user)
        db.commit()
        account = repo.create_account(db, user_id=user.id, handle="stale-user")
        stale = repo.create_job(db, account_id=account.id, job_type="incremental")
        stale.status = "running"
        stale.updated_at = datetime.now(UTC) - timedelta(hours=3)
        db.commit()
        stale_id = stale.id

    summary = cf_tasks.dispatch_scheduled_syncs.delay().get()

    assert summary["recovered_stale"] == 1
    with sqlite_session_factory() as db:
        job = db.get(SyncJob, stale_id)
        assert job.status == "failed"
        assert "stale" in job.error_summary
