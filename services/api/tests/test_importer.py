"""Importer tests: pagination, idempotency, first-solve semantics, failures.

All Codeforces payloads are fixtures consumed by a FakeClient — no network.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.integrations.codeforces.client import CfApiError, CfTransientError
from app.models import CfAccount, Problem, Submission, SyncJob, UserProblem
from app.repositories import codeforces as repo
from app.services.sync.importer import SyncImporter

T0 = datetime(2024, 5, 1, 12, 0, tzinfo=UTC)


def as_utc(dt):
    """SQLite loses tzinfo on reload; PostgreSQL (CI/prod) preserves it."""
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def cf_problem(contest=1, index="A", name=None, rating=1000, tags=("math",)):
    return {
        "contestId": contest,
        "index": index,
        "name": name or f"Problem {index}",
        "rating": rating,
        "tags": list(tags),
    }


def cf_item(sub_id, ts: datetime, verdict, problem):
    return {
        "id": sub_id,
        "creationTimeSeconds": int(ts.timestamp()),
        "problem": problem,
        "author": {"members": [{"handle": "tourist"}], "participationType": "PRACTICE"},
        "programmingLanguage": "PyPy 3",
        "verdict": verdict,
        "passedTestCount": 30 if verdict == "OK" else 0,
        "timeConsumedMillis": 100,
        "memoryConsumedBytes": 2000,
    }


class FakeClient:
    def __init__(self, pages: list[list[dict]], raise_at: dict[int, Exception] | None = None):
        self.pages = pages
        self.raise_at = raise_at or {}
        self.status_requests: list[tuple[int, int]] = []
        self.info_calls = 0

    def get_user_info(self, handle):
        self.info_calls += 1
        return {"handle": handle, "rating": 3000}

    def fetch_status_page(self, handle, from_, count):
        self.status_requests.append((from_, count))
        page_index = (from_ - 1) // count
        if page_index in self.raise_at:
            raise self.raise_at[page_index]
        return self.pages[page_index] if page_index < len(self.pages) else []


def make_importer(db_session, account, client, *, page_size=2, hist=50, incr=10) -> SyncImporter:
    return SyncImporter(
        db_session,
        account,
        client,
        page_size=page_size,
        historical_max_pages=hist,
        incremental_max_pages=incr,
    )


@pytest.fixture
def account(db_session, make_user) -> CfAccount:
    user = make_user("importer@example.com")
    return repo.create_account(db_session, user_id=user.id, handle="tourist")


def run_historical(db_session, account, client, job=None) -> SyncJob:
    job = job or repo.create_job(db_session, account_id=account.id, job_type="historical")
    make_importer(db_session, account, client).run(job)
    db_session.expire_all()
    return job


def submissions(db_session, account) -> list[Submission]:
    return list(
        db_session.query(Submission)
        .filter(Submission.cf_account_id == account.id)
        .order_by(Submission.cf_submission_id)
    )


def rollups(db_session, user_id) -> list[UserProblem]:
    return list(db_session.query(UserProblem).filter(UserProblem.user_id == user_id))


# ------------------------------------------------------------------ imports


def test_accepted_vs_rejected_and_first_solve(db_session, account, make_user):
    user_id = account.user_id
    problem = cf_problem()
    client = FakeClient(
        [
            [
                cf_item(2, T0 + timedelta(days=1), "OK", problem),
                cf_item(1, T0, "WRONG_ANSWER", problem),
            ]
        ]
    )
    run_historical(db_session, account, client)

    subs = submissions(db_session, account)
    assert [(s.cf_submission_id, s.verdict) for s in subs] == [(1, "WRONG_ANSWER"), (2, "OK")]

    ups = rollups(db_session, user_id)
    assert len(ups) == 1
    assert as_utc(ups[0].first_solved_at) == T0 + timedelta(days=1)  # the accepted one only
    assert ups[0].accepted_count == 1


def test_multiple_accepted_and_out_of_order_timestamps(db_session, account):
    problem = cf_problem()
    later_ok = T0 + timedelta(days=10)
    earlier_ok = T0 - timedelta(days=5)  # older solve arrives with a HIGHER id
    client = FakeClient(
        [
            [
                cf_item(3, later_ok, "OK", problem),
                cf_item(2, T0, "WRONG_ANSWER", problem),
            ],
            [cf_item(1, earlier_ok, "OK", problem)],
        ]
    )
    run_historical(db_session, account, client)

    up = rollups(db_session, account.user_id)[0]
    assert as_utc(up.first_solved_at) == earlier_ok  # min over accepted, ids irrelevant
    assert as_utc(up.last_solved_at) == later_ok
    assert up.accepted_count == 2


def test_pagination_walks_all_pages_with_correct_offsets(db_session, account):
    problem = cf_problem()
    client = FakeClient(
        [
            [cf_item(4, T0, "OK", problem), cf_item(3, T0, "OK", problem)],
            [cf_item(2, T0, "OK", problem), cf_item(1, T0, "OK", problem)],
            [cf_item(0 + 100, T0, "OK", cf_problem(2, "B"))],  # short final page
        ]
    )
    job = run_historical(db_session, account, client)

    assert client.status_requests == [(1, 2), (3, 2), (5, 2)]
    assert len(submissions(db_session, account)) == 5
    assert job.status == "succeeded"
    assert job.progress == {"pages_fetched": 3, "submissions_seen": 5, "new_submissions": 5}


def test_reimport_is_idempotent(db_session, account):
    problem = cf_problem()
    pages = [[cf_item(2, T0 + timedelta(days=1), "OK", problem), cf_item(1, T0, "OK", problem)]]

    run_historical(db_session, account, FakeClient(pages))
    before_subs = submissions(db_session, account)
    before_ups = rollups(db_session, account.user_id)

    job = run_historical(db_session, account, FakeClient(pages))  # fresh client, same data

    after_subs = submissions(db_session, account)
    assert len(after_subs) == len(before_subs) == 2
    assert rollups(db_session, account.user_id)[0].accepted_count == 2
    assert job.progress["new_submissions"] == 0
    assert job.status == "succeeded"
    assert before_ups[0].first_solved_at == rollups(db_session, account.user_id)[0].first_solved_at


def test_verdict_refresh_testing_to_ok(db_session, account):
    problem = cf_problem()
    run_historical(
        db_session,
        account,
        FakeClient([[cf_item(1, T0, "TESTING", problem)]]),
    )
    assert rollups(db_session, account.user_id) == []

    job = repo.create_job(db_session, account_id=account.id, job_type="incremental")
    make_importer(db_session, account, FakeClient([[cf_item(1, T0, "OK", problem)]])).run(job)
    db_session.expire_all()

    assert len(submissions(db_session, account)) == 1  # updated, not duplicated
    assert submissions(db_session, account)[0].verdict == "OK"
    assert as_utc(rollups(db_session, account.user_id)[0].first_solved_at) == T0


def test_earlier_discovery_moves_first_solved_back_not_forward(db_session, account):
    problem = cf_problem()
    original = T0
    run_historical(db_session, account, FakeClient([[cf_item(1, original, "OK", problem)]]))

    much_earlier = T0 - timedelta(days=100)
    job = repo.create_job(db_session, account_id=account.id, job_type="incremental")
    make_importer(
        db_session,
        account,
        FakeClient(
            [[cf_item(9, much_earlier, "OK", problem), cf_item(1, original, "OK", problem)]]
        ),
    ).run(job)
    db_session.expire_all()

    up = rollups(db_session, account.user_id)[0]
    assert as_utc(up.first_solved_at) == much_earlier  # moved EARLIER (min semantics)


def test_later_submission_never_overwrites_first_solved(db_session, account):
    problem = cf_problem()
    run_historical(db_session, account, FakeClient([[cf_item(1, T0, "OK", problem)]]))

    job = repo.create_job(db_session, account_id=account.id, job_type="incremental")
    make_importer(
        db_session,
        account,
        FakeClient(
            [[cf_item(2, T0 + timedelta(days=30), "OK", problem), cf_item(1, T0, "OK", problem)]]
        ),
    ).run(job)
    db_session.expire_all()

    assert as_utc(rollups(db_session, account.user_id)[0].first_solved_at) == T0


def test_empty_history_succeeds_with_no_data(db_session, account):
    job = run_historical(db_session, account, FakeClient([[]]))
    db_session.expire(account, ["verified_at", "last_synced_at"])

    assert job.status == "succeeded"
    assert submissions(db_session, account) == []
    assert rollups(db_session, account.user_id) == []
    assert account.verified_at is not None  # user.info validated the handle
    assert account.last_synced_at is not None
    assert account.last_sync_error is None


def test_missing_contest_metadata_uses_fallback_identity(db_session, account):
    gym = cf_problem(contest=None, index=None, name="Mysterious Gym Problem")
    gym["problemsetName"] = "acmsguru"
    client = FakeClient([[cf_item(1, T0, "OK", gym)]])
    run_historical(db_session, account, client)

    up = rollups(db_session, account.user_id)[0]
    refreshed = db_session.get(Problem, up.problem_id)
    assert refreshed.canonical_key == "ps:acmsguru:mysterious-gym-problem"


def test_incremental_stops_when_page_fully_known(db_session, account):
    problem = cf_problem()
    run_historical(
        db_session,
        account,
        FakeClient([[cf_item(2, T0, "OK", problem), cf_item(1, T0, "OK", problem)]]),
    )

    client = FakeClient(
        [
            [cf_item(2, T0, "OK", problem), cf_item(1, T0, "OK", problem)],  # all known
            [cf_item(0, T0, "OK", problem)],  # must NOT be fetched
        ]
    )
    job = repo.create_job(db_session, account_id=account.id, job_type="incremental")
    make_importer(db_session, account, client).run(job)

    assert len(client.status_requests) == 1  # stopped at the fully-known page
    assert len(submissions(db_session, account)) == 2


def test_transient_failure_keeps_cursor_and_marks_job_failed(db_session, account):
    problem = cf_problem()
    client = FakeClient(
        [[cf_item(2, T0, "OK", problem), cf_item(1, T0, "OK", problem)]],
        raise_at={1: CfTransientError("CF down after 3 attempts")},
    )
    job = repo.create_job(db_session, account_id=account.id, job_type="historical")

    with pytest.raises(CfTransientError):
        make_importer(db_session, account, client).run(job)
    db_session.expire_all()

    assert job.status == "failed"
    assert "CF down" in job.error_summary
    # Page 1 committed (resumable), but the run was NOT marked complete.
    assert len(submissions(db_session, account)) == 2
    assert account.last_synced_at is None
    assert account.sync_cursor is None
    assert "CF down" in account.last_sync_error

    # Resume: a fresh job re-walks idempotently and completes.
    client2 = FakeClient([[cf_item(2, T0, "OK", problem), cf_item(1, T0, "OK", problem)]])
    job2 = repo.create_job(db_session, account_id=account.id, job_type="historical")
    make_importer(db_session, account, client2).run(job2)
    db_session.expire_all()
    assert job2.status == "succeeded"
    assert account.last_synced_at is not None
    assert account.sync_cursor == {"last_seen_submission_id": 2}


def test_page_cap_exceeded_fails_instead_of_partial_success(db_session, account):
    problem = cf_problem()
    full_page = [cf_item(i, T0, "OK", problem) for i in range(1, 3)]  # page_size=2, never short
    client = FakeClient([full_page] * 10)  # endless full pages
    job = repo.create_job(db_session, account_id=account.id, job_type="historical")

    with pytest.raises(CfApiError, match="exceeded"):
        make_importer(db_session, account, client, hist=3).run(job)
    db_session.expire_all()
    assert job.status == "failed"


def test_concurrent_running_job_cancels_this_one(db_session, account):
    winner = repo.create_job(db_session, account_id=account.id, job_type="incremental")
    winner.status = "running"
    db_session.commit()

    loser = repo.create_job(db_session, account_id=account.id, job_type="incremental")
    client = FakeClient([[cf_item(1, T0, "OK", cf_problem())]])
    make_importer(db_session, account, client).run(loser)  # no exception
    db_session.expire_all()

    assert loser.status == "cancelled"
    assert "concurrent" in loser.error_summary
    assert client.status_requests == []  # never fetched anything
    assert account.last_synced_at is None


def test_cursor_persists_max_seen_id_not_timestamp(db_session, account):
    problem = cf_problem()
    later_id_smaller_ts = cf_item(50, T0 - timedelta(days=9), "OK", problem)
    earlier_id_later_ts = cf_item(7, T0, "OK", problem)
    run_historical(db_session, account, FakeClient([[later_id_smaller_ts, earlier_id_later_ts]]))
    db_session.expire(account, ["sync_cursor"])

    assert account.sync_cursor == {"last_seen_submission_id": 50}  # max id, not latest time


def test_problem_metadata_refreshes_on_reimport(db_session, account):
    problem_v1 = cf_problem(rating=None)
    run_historical(db_session, account, FakeClient([[cf_item(1, T0, "OK", problem_v1)]]))

    problem_v2 = cf_problem(rating=2100, tags=("math", "greedy"))
    run_historical(db_session, account, FakeClient([[cf_item(1, T0, "OK", problem_v2)]]))
    db_session.expire_all()

    refreshed = db_session.query(Problem).filter(Problem.canonical_key == "1-A").one()
    assert refreshed.rating == 2100
    assert refreshed.tags == ["math", "greedy"]
    assert rollups(db_session, account.user_id)[0].accepted_count == 1


def test_importer_isolates_users(db_session, account, make_user):
    other = make_user("other@example.com")
    assert other.id != account.user_id
    run_historical(db_session, account, FakeClient([[cf_item(1, T0, "OK", cf_problem())]]))
    # Rollups exist only for the account owner.
    assert rollups(db_session, account.user_id)
    assert rollups(db_session, other.id) == []
