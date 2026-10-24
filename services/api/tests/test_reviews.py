"""Review lifecycle tests: outcomes, atomicity, idempotency, isolation, tz.

Seeded through the Phase 1 importer fixtures; fake clock passed into the
service for deterministic due dates; no network.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import sessionmaker

from app.integrations.fsrs import adapter
from app.models import MemoryState, ReviewSession, UserProblem
from app.repositories import codeforces as cf_repo
from app.repositories import reviews as repo
from app.services import reviews as service
from tests.test_importer import FakeClient, cf_item, cf_problem, run_historical

T0 = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
P = cf_problem(1, "A", name="Theatre Square", rating=1000, tags=("math",))


@pytest.fixture
def seeded_problem_id(db_session, auth_client) -> uuid.UUID:
    """Dev user with one solved problem; returns the problems.id."""
    user = auth_client.user
    account = cf_repo.create_account(db_session, user_id=user.id, handle="tourist")
    run_historical(db_session, account, FakeClient([[cf_item(1, T0, "OK", P)]]))
    problem_id = db_session.query(UserProblem).filter_by(user_id=user.id).one().problem_id
    db_session.expire_all()
    return problem_id


def start(auth_client, problem_id):
    resp = auth_client.post("/api/v1/reviews/sessions", json={"problem_id": str(problem_id)})
    assert resp.status_code == 201, resp.text
    return resp.json()


def complete(auth_client, session_id, **over):
    payload = {"outcome": "good", "independent": True, **over}
    return auth_client.post(f"/api/v1/reviews/sessions/{session_id}/complete", json=payload)


# ------------------------------------------------------------- lifecycle


def test_start_and_complete_returns_next_due(auth_client, seeded_problem_id):
    created = start(auth_client, seeded_problem_id)
    assert created["session"]["status"] == "pending"
    assert created["problem"]["name"] == "Theatre Square"
    assert created["memory"] is None  # CF acceptance is not a review

    resp = complete(auth_client, created["session"]["id"])
    assert resp.status_code == 200
    body = resp.json()
    assert body["session"]["status"] == "completed"
    assert body["session"]["outcome"] == "good"
    assert body["memory"]["repetitions"] == 1
    assert body["memory"]["due_at"] > body["session"]["completed_at"]
    assert body["memory"]["scheduler_version"] == adapter.SCHEDULER_VERSION


@pytest.mark.parametrize(
    "outcome,independent,verified",
    [
        ("again", True, False),
        ("hard", True, False),
        ("good", True, True),
        ("easy", True, True),
        ("good", False, False),  # assisted Good is NOT independent recall
    ],
)
def test_outcome_and_independence_policy(
    auth_client, db_session, seeded_problem_id, outcome, independent, verified
):
    created = start(auth_client, seeded_problem_id)
    resp = complete(auth_client, created["session"]["id"], outcome=outcome, independent=independent)
    assert resp.status_code == 200

    rollup = db_session.query(UserProblem).filter_by(user_id=auth_client.user.id).one()
    assert rollup.independent_solve_verified is verified


def test_help_level_recorded_separately_from_rating(auth_client, seeded_problem_id):
    created = start(auth_client, seeded_problem_id)
    resp = complete(
        auth_client,
        created["session"]["id"],
        outcome="hard",
        independent=False,
        help_level="editorial",
        duration_seconds=420,
        notes="needed the editorial idea",
    )
    body = resp.json()
    assert body["session"]["help_level"] == "editorial"
    assert body["session"]["independent"] is False
    assert body["session"]["outcome"] == "hard"  # rating unchanged by help info
    assert body["session"]["duration_seconds"] == 420


def test_second_completion_conflicts_without_advancing(auth_client, db_session, seeded_problem_id):
    created = start(auth_client, seeded_problem_id)
    first = complete(auth_client, created["session"]["id"])
    assert first.status_code == 200
    first.json()["memory"]["due_at"]
    reps_after_first = first.json()["memory"]["repetitions"]

    second = complete(auth_client, created["session"]["id"])
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "http_409"

    memory = db_session.query(MemoryState).one()
    assert memory.repetitions == reps_after_first  # FSRS advanced exactly once


def test_invalid_outcome_and_payloads_rejected(auth_client, seeded_problem_id):
    created = start(auth_client, seeded_problem_id)
    for bad in (
        {"outcome": "perfect"},
        {"outcome": "good", "duration_seconds": -5},
        {"outcome": "good", "help_level": "telepathy"},
        {"outcome": "good", "notes": "x" * 3000},
    ):
        resp = auth_client.post(
            f"/api/v1/reviews/sessions/{created['session']['id']}/complete", json=bad
        )
        assert resp.status_code == 422, bad


def test_unknown_problem_and_session_return_404(auth_client, seeded_problem_id):
    resp = auth_client.post(
        "/api/v1/reviews/sessions", json={"problem_id": str(uuid.uuid4())}
    )
    assert resp.status_code == 404
    assert "solved" in resp.json()["error"]["message"]

    resp = auth_client.post(
        f"/api/v1/reviews/sessions/{uuid.uuid4()}/complete", json={"outcome": "good"}
    )
    assert resp.status_code == 404


def test_cross_user_isolation_without_existence_leak(
    auth_client, seeded_problem_id, make_auth_client, db_session
):
    created = start(auth_client, seeded_problem_id)
    other = make_auth_client("intruder@example.com")

    resp = other.post(
        f"/api/v1/reviews/sessions/{created['session']['id']}/complete",
        json={"outcome": "good"},
    )
    assert resp.status_code == 404  # same shape as unknown session
    assert resp.json()["error"]["code"] == "http_404"
    assert other.get(f"/api/v1/reviews/sessions/{created['session']['id']}").status_code == 404

    # The original owner can still complete it.
    assert complete(auth_client, created["session"]["id"]).status_code == 200


def test_due_list_and_overdue_ordering(auth_client, db_session, seeded_problem_id):
    # Far-future fake clock so the real wall time can never make it due.
    now = datetime(2027, 1, 1, 12, 0, tzinfo=UTC)
    created = start(auth_client, seeded_problem_id)
    service.complete_review(
        db_session,
        user_id=auth_client.user.id,
        session_id=uuid.UUID(created["session"]["id"]),
        outcome="good",
        independent=True,
        help_level=None,
        duration_seconds=None,
        notes=None,
        now=now,
    )
    # Due 10 minutes after `now` (learning step) — not yet due at `now`.
    due = auth_client.get("/api/v1/reviews/due").json()
    assert due["items"] == []

    # Force the stored due date into the past relative to the REAL clock
    # (the endpoint compares against wall time).
    db_session.query(MemoryState).update({"due_at": datetime.now(UTC) - timedelta(days=3)})
    db_session.commit()
    due = auth_client.get("/api/v1/reviews/due").json()
    assert len(due["items"]) == 1
    assert due["items"][0]["problem"]["name"] == "Theatre Square"
    assert due["items"][0]["repetitions"] == 1


def test_history_lists_completed_only(auth_client, seeded_problem_id):
    pending = start(auth_client, seeded_problem_id)  # never completed
    done = start(auth_client, seeded_problem_id)
    assert complete(auth_client, done["session"]["id"]).status_code == 200

    history = auth_client.get("/api/v1/reviews/history").json()
    assert history["total"] == 1
    assert history["items"][0]["outcome"] == "good"
    assert history["items"][0]["id"] != pending["session"]["id"]


# --------------------------------------------- atomicity / restarts / corruption


def test_review_and_memory_rollback_together(
    auth_client, db_session, seeded_problem_id, monkeypatch
):
    created = start(auth_client, seeded_problem_id)

    def boom(*args, **kwargs):
        raise RuntimeError("scheduler exploded")

    monkeypatch.setattr(repo, "upsert_memory", boom)
    with pytest.raises(RuntimeError):
        service.complete_review(
            db_session,
            user_id=auth_client.user.id,
            session_id=uuid.UUID(created["session"]["id"]),
            outcome="good",
            independent=True,
            help_level=None,
            duration_seconds=None,
            notes=None,
        )
    db_session.rollback()
    db_session.expire_all()

    assert db_session.query(ReviewSession).one().status == "pending"
    assert db_session.query(MemoryState).count() == 0  # nothing persisted


def test_state_survives_session_restart(db_session, auth_client, seeded_problem_id, db_engine):
    now = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
    created = start(auth_client, seeded_problem_id)
    service.complete_review(
        db_session,
        user_id=auth_client.user.id,
        session_id=uuid.UUID(created["session"]["id"]),
        outcome="good",
        independent=True,
        help_level=None,
        duration_seconds=None,
        notes=None,
        now=now,
    )

    # Brand-new sessionmaker over the same engine = process restart.
    factory = sessionmaker(bind=db_engine, expire_on_commit=False)
    with factory() as fresh:
        memory = fresh.query(MemoryState).one()
        assert memory.repetitions == 1
        restored = adapter.card_view(memory.scheduler_state)
        assert restored["stability"] == pytest.approx(2.3065)

        # A later review through the restarted session continues the state.
        review2 = service.start_review(
            fresh, user_id=auth_client.user.id, problem_id=seeded_problem_id
        )
        service.complete_review(
            fresh,
            user_id=auth_client.user.id,
            session_id=review2.id,
            outcome="easy",
            independent=True,
            help_level=None,
            duration_seconds=None,
            notes=None,
            now=now + timedelta(days=1),
        )
        memory = fresh.query(MemoryState).one()
        assert memory.repetitions == 2
        view = adapter.card_view(memory.scheduler_state)
        # Good(+1d) then Easy: Review state, 12-day interval from that review.
        assert view["due_at"] == now + timedelta(days=13)


def test_corrupt_memory_state_never_silently_reset(auth_client, db_session, seeded_problem_id):
    created = start(auth_client, seeded_problem_id)
    complete(auth_client, created["session"]["id"])  # first review OK

    # Corrupt the serialized state directly.
    memory = db_session.query(MemoryState).one()
    memory.scheduler_state = {"version": "fsrs-0.0.1", "card": {}, "scheduler": {}}
    db_session.commit()

    second = start(auth_client, seeded_problem_id)
    resp = complete(auth_client, second["session"]["id"])
    assert resp.status_code == 500
    assert "corrupt" in resp.json()["error"]["message"].lower()

    db_session.expire_all()
    memory = db_session.query(MemoryState).one()
    assert memory.repetitions == 1  # untouched by the failed attempt
    assert db_session.query(ReviewSession).filter_by(status="completed").count() == 1


def test_overdue_again_shortens_vs_easy_path(auth_client, db_session, seeded_problem_id):
    """Again on a graduated card must NOT push the due date further out."""
    now = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
    user_id = auth_client.user.id

    s1 = service.start_review(db_session, user_id=user_id, problem_id=seeded_problem_id)
    service.complete_review(db_session, user_id=user_id, session_id=s1.id, outcome="good",
                            independent=True, help_level=None, duration_seconds=None,
                            notes=None, now=now)
    s2 = service.start_review(db_session, user_id=user_id, problem_id=seeded_problem_id)
    done, memory = service.complete_review(db_session, user_id=user_id, session_id=s2.id,
                                            outcome="easy", independent=True, help_level=None,
                                            duration_seconds=None, notes=None,
                                            now=now + timedelta(days=1))
    graduated_due = memory.due_at
    assert graduated_due > now + timedelta(days=1)

    s3 = service.start_review(db_session, user_id=user_id, problem_id=seeded_problem_id)
    _, memory_after_again = service.complete_review(
        db_session, user_id=user_id, session_id=s3.id, outcome="again",
        independent=True, help_level=None, duration_seconds=None, notes=None,
        now=now + timedelta(days=2),
    )
    assert memory_after_again.due_at < graduated_due  # lapse shortens the horizon
    assert memory_after_again.lapses == 1
    assert memory_after_again.repetitions == 3


# ---------------------------------------------------------------- heatmap


def test_reviews_heatmap_counts_completed_sessions_by_local_date(
    auth_client, db_session, seeded_problem_id
):
    completed_at = datetime(2026, 10, 24, 23, 30, tzinfo=UTC)  # UTC-midnight boundary
    for _i in range(2):
        review = service.start_review(
            db_session, user_id=auth_client.user.id, problem_id=seeded_problem_id
        )
        service.complete_review(
            db_session,
            user_id=auth_client.user.id,
            session_id=review.id,
            outcome="good",
            independent=True,
            help_level=None,
            duration_seconds=None,
            notes=None,
            now=completed_at,
        )
    # A started-but-never-completed session must not count.
    service.start_review(db_session, user_id=auth_client.user.id, problem_id=seeded_problem_id)

    utc = auth_client.get(
        "/api/v1/dashboard/heatmap?from=2026-10-24&to=2026-10-24&timezone=UTC&mode=reviews"
    ).json()
    assert utc["available"] is True
    assert utc["days"][0]["count"] == 2

    kolkata = auth_client.get(
        "/api/v1/dashboard/heatmap"
        "?from=2026-10-25&to=2026-10-25&timezone=Asia/Kolkata&mode=reviews"
    ).json()
    # 23:30 UTC on 10-24 is already 10-25 in Kolkata (+5:30).
    assert kolkata["days"][0]["count"] == 2


def test_reviews_heatmap_zero_when_no_sessions(make_auth_client):
    fresh = make_auth_client("quiet@example.com")
    body = fresh.get(
        "/api/v1/dashboard/heatmap?from=2026-10-01&to=2026-10-05&timezone=UTC&mode=reviews"
    ).json()
    assert body["available"] is True
    assert [d["count"] for d in body["days"]] == [0, 0, 0, 0, 0]
