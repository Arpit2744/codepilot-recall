"""Queue urgency-layer tests: tiers, boundaries, ordering, risk, isolation.

Classification is unit-tested with explicit clocks (no sleeps); endpoint
behavior is tested with due dates forced relative to the real clock.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.integrations.fsrs import adapter
from app.models import MemoryState, UserProblem
from app.repositories import codeforces as cf_repo
from app.services import queue as queue_service
from app.services import reviews as service
from tests.test_importer import FakeClient, cf_item, cf_problem, run_historical

T0 = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
NOW = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)

PROBLEMS = [
    cf_problem(1, "A", name="Alpha", rating=1000, tags=("math",)),
    cf_problem(2, "B", name="Bravo", rating=1200, tags=("dp",)),
    cf_problem(3, "C", name="Charlie", rating=1400, tags=("greedy",)),
    cf_problem(4, "D", name="Delta", rating=1600, tags=("graphs",)),
]


def _item(due_at, retrievability=None, stability=None, key="1-A", unavailable=False):
    return {
        "due_at": due_at,
        "retrievability": retrievability,
        "stability": stability,
        "canonical_key": key,
        "estimate_unavailable": unavailable,
    }


# ------------------------------------------------------ pure classification


def test_status_boundary_exactly_at_and_below_threshold():
    at_threshold = queue_service.classify_due(
        _item(NOW - timedelta(seconds=86_400)), now=NOW
    )
    assert at_threshold["status"] == "overdue"  # >= 24h past due
    assert at_threshold["overdue_seconds"] == 86_400

    just_below = queue_service.classify_due(
        _item(NOW - timedelta(seconds=86_399)), now=NOW
    )
    assert just_below["status"] == "due"
    assert just_below["priority_tier"] == 4
    assert just_below["priority_reason"] == "Due now"


def test_priority_tiers_by_overdue_duration():
    cases = [
        # Policy: "overdue" starts past a 24h grace window (tier 3).
        (timedelta(hours=30), 3, "Overdue by 1 day"),
        (timedelta(days=8), 2, "Overdue by 8 days"),
        (timedelta(days=31), 1, "Overdue by 31 days"),
    ]
    for delta, tier, fragment in cases:
        result = queue_service.classify_due(_item(NOW - delta), now=NOW)
        assert result["priority_tier"] == tier, delta
        assert fragment in result["priority_reason"]
        assert result["status"] == "overdue"


def test_reason_includes_risk_only_when_estimate_exists():
    with_risk = queue_service.classify_due(
        _item(NOW - timedelta(days=8), retrievability=0.42), now=NOW
    )
    assert "estimated recall ≈ 42%" in with_risk["priority_reason"]
    assert "low estimated retrievability" in with_risk["priority_reason"]
    assert with_risk["risk"] == "high"

    without = queue_service.classify_due(_item(NOW - timedelta(days=8)), now=NOW)
    assert "estimated recall" not in without["priority_reason"]
    assert without["risk"] is None

    unavailable = queue_service.classify_due(
        _item(NOW - timedelta(days=8), unavailable=True), now=NOW
    )
    assert "recall estimate unavailable" in unavailable["priority_reason"]


def test_risk_bands_documented_thresholds():
    assert queue_service.risk_category(0.49) == "high"
    assert queue_service.risk_category(0.79) == "elevated"
    assert queue_service.risk_category(0.81) == "low"
    assert queue_service.risk_category(None) is None


def test_ordering_tier_then_overdue_then_stability_then_key():
    def queued(delta, stability, key):
        item = _item(NOW - delta, stability=stability, key=key)
        item.update(queue_service.classify_due(item, now=NOW))
        return item

    items = [
        queued(timedelta(days=8), 5.0, "2-B"),
        queued(timedelta(days=9), 5.0, "1-A"),   # most overdue in tier 2
        queued(timedelta(hours=2), 1.0, "3-C"),  # inside grace: tier 4
        queued(timedelta(hours=1), None, "4-D"), # tier 4, less overdue
        queued(timedelta(days=8), 2.0, "9-Z"),   # same tier/overdue: weaker first
        queued(timedelta(days=8), 5.0, "1-B"),   # identical: key tiebreak
    ]
    ordered = queue_service.order_due_queue(items)
    keys = [i["canonical_key"] for i in ordered]
    # Tier 2 first: 9d-overdue leads; then the 8d group by stability asc
    # (9-Z) and canonical key (1-B before 2-B). Tier 4 last, most overdue
    # first.
    assert keys == ["1-A", "9-Z", "1-B", "2-B", "3-C", "4-D"]


def test_upcoming_classification_never_labeled_due():
    result = queue_service.classify_upcoming(_item(NOW + timedelta(hours=3)), now=NOW)
    assert result["status"] == "upcoming"
    assert result["seconds_until_due"] == 3 * 3600
    assert result["priority_tier"] is None
    assert result["priority_reason"] == "Scheduled in 3 hours"


# ------------------------------------------------ retrievability (adapter)


def test_retrievability_decays_and_is_pure():
    state = adapter.apply_review(None, "good", now=NOW)
    state = adapter.apply_review(state, "easy", now=NOW + timedelta(days=1))
    snapshot = state["card"]

    soon = adapter.retrievability(state, at=NOW + timedelta(days=1, hours=1))
    later = adapter.retrievability(state, at=NOW + timedelta(days=10))
    latest = adapter.retrievability(state, at=NOW + timedelta(days=30))

    assert soon == pytest.approx(1.0)
    assert later < soon
    assert latest < later
    # Pure query: the serialized card is untouched.
    assert state["card"] == snapshot


def test_retrievability_absent_and_corrupt_states():
    assert adapter.retrievability(None, at=NOW) is None
    fresh = adapter.new_state(NOW)  # card with no review history
    assert adapter.retrievability(fresh, at=NOW) is None
    with pytest.raises(adapter.MemoryStateCorrupt):
        adapter.retrievability({"version": "bogus"}, at=NOW)


def test_retrievability_consistent_after_restoration():
    state = adapter.apply_review(None, "good", now=NOW)
    # Round-trip through the serialized form (as stored in memory_states).
    restored = dict(state)
    direct = adapter.retrievability(state, at=NOW + timedelta(days=5))
    again = adapter.retrievability(restored, at=NOW + timedelta(days=5))
    assert direct == again == pytest.approx(direct)


# ------------------------------------------------------------ endpoint


@pytest.fixture
def seeded_user(auth_client, db_session):
    user = auth_client.dev_user
    account = cf_repo.create_account(db_session, user_id=user.id, handle="tourist")
    run_historical(
        db_session,
        account,
        FakeClient([[cf_item(i + 1, T0, "OK", PROBLEMS[i]) for i in range(3)]]),
    )
    # Complete one review per solved problem so memory states exist.
    problem_ids = [
        row.problem_id
        for row in db_session.query(UserProblem).filter_by(user_id=user.id).all()
    ]
    for pid in problem_ids:
        review = service.start_review(db_session, user_id=user.id, problem_id=pid)
        service.complete_review(
            db_session,
            user_id=user.id,
            session_id=review.id,
            outcome="good",
            independent=True,
            help_level=None,
            duration_seconds=None,
            notes=None,
            now=T0,
        )
    db_session.expire_all()
    return user, problem_ids


def _force_due(db_session, user_id, offsets: dict):
    """Force due dates relative to the REAL clock (endpoint uses wall time)."""
    memories = (
        db_session.query(MemoryState)
        .filter_by(user_id=user_id)
        .order_by(MemoryState.created_at)
        .all()
    )
    now = datetime.now(UTC)
    for memory, (hours, stability) in zip(memories, offsets.values(), strict=False):
        memory.due_at = now - timedelta(hours=hours)
        memory.stability = stability
    db_session.commit()
    db_session.expire_all()


def test_queue_endpoint_ranks_and_labels(auth_client, db_session, seeded_user):
    user, problem_ids = seeded_user
    _force_due(
        db_session,
        user.id,
        {"a": (2, 5.0), "b": (8 * 24, 5.0), "c": (31 * 24, 1.0)},
    )

    body = auth_client.get("/api/v1/reviews/due").json()
    assert body["mode"] == "due"
    tiers = [item["priority_tier"] for item in body["items"]]
    # 31d -> tier 1, 8d -> tier 2, 2h (inside the 24h grace) -> tier 4.
    assert tiers == [1, 2, 4]

    critical = body["items"][0]
    assert critical["status"] == "overdue"
    assert critical["overdue_seconds"] >= 30 * 86_400
    assert "Critical priority" in critical["priority_reason"]
    assert "Overdue by 31 days" in critical["priority_reason"]
    # Retrievability present and a valid band (model estimate).
    assert 0.0 <= critical["retrievability"] <= 1.0
    assert critical["risk"] in ("high", "elevated", "low")
    assert critical["stability"] == 1.0

    just_due = body["items"][2]
    assert just_due["status"] == "due"
    assert just_due["priority_reason"].startswith("Due now")
    # The 2h-past-due item has a fresh review: estimate near 100%.
    assert "model estimate" in just_due["priority_reason"]


def test_queue_limit_is_bounded(auth_client, db_session, seeded_user):
    user, _ = seeded_user
    _force_due(db_session, user.id, {"a": (2, 5.0), "b": (3, 5.0), "c": (4, 5.0)})
    body = auth_client.get("/api/v1/reviews/due?limit=2").json()
    assert len(body["items"]) == 2


def test_queue_user_isolation(auth_client, db_session, seeded_user, make_user):
    user, _ = seeded_user
    _force_due(db_session, user.id, {"a": (2, 5.0), "b": (3, 5.0), "c": (4, 5.0)})
    other = make_user("queueless@example.com")
    body = auth_client.get(
        "/api/v1/reviews/due", headers={"X-User-Id": str(other.id)}
    ).json()
    assert body["items"] == []


def test_queue_corrupt_state_ranked_with_explicit_unavailable_estimate(
    auth_client, db_session, seeded_user
):
    user, _ = seeded_user
    _force_due(db_session, user.id, {"a": (2, 5.0), "b": (8 * 24, 5.0), "c": (4, 5.0)})
    memories = db_session.query(MemoryState).filter_by(user_id=user.id).all()
    corrupt = max(memories, key=lambda m: m.due_at)  # the least-urgent one
    corrupt.scheduler_state = {"version": "fsrs-0.0.1", "card": {}, "scheduler": {}}
    db_session.commit()

    body = auth_client.get("/api/v1/reviews/due").json()
    flagged = [i for i in body["items"] if i["retrievability"] is None]
    assert len(flagged) == 1
    assert flagged[0]["risk"] is None
    assert "estimate unavailable" in flagged[0]["priority_reason"]
    # Still ranked by its due-date fact; still present (not hidden).
    assert flagged[0] in body["items"]


def test_queue_read_never_mutates_memory(auth_client, db_session, seeded_user):
    user, _ = seeded_user
    _force_due(db_session, user.id, {"a": (2, 5.0), "b": (3, 5.0), "c": (4, 5.0)})
    before = {
        str(m.id): (m.due_at, m.repetitions, str(m.scheduler_state))
        for m in db_session.query(MemoryState).filter_by(user_id=user.id).all()
    }

    auth_client.get("/api/v1/reviews/due")

    db_session.expire_all()
    after = {
        str(m.id): (m.due_at, m.repetitions, str(m.scheduler_state))
        for m in db_session.query(MemoryState).filter_by(user_id=user.id).all()
    }
    assert before == after


def test_completed_review_leaves_queue_and_reschedules_future(
    auth_client, db_session, seeded_user
):
    user, problem_ids = seeded_user
    _force_due(db_session, user.id, {"a": (2, 5.0), "b": (3, 5.0), "c": (4, 5.0)})
    assert len(auth_client.get("/api/v1/reviews/due").json()["items"]) == 3

    # Complete one problem with an independent Good at the real clock.
    created = auth_client.post(
        "/api/v1/reviews/sessions", json={"problem_id": str(problem_ids[0])}
    ).json()
    done = auth_client.post(
        f"/api/v1/reviews/sessions/{created['session']['id']}/complete",
        json={"outcome": "good", "independent": True},
    )
    assert done.status_code == 200
    assert done.json()["memory"]["due_at"] > done.json()["session"]["completed_at"]

    queue = auth_client.get("/api/v1/reviews/due").json()
    assert len(queue["items"]) == 2  # rescheduled into the future: gone


def test_failed_completion_keeps_queue_and_history_intact(
    auth_client, db_session, seeded_user, monkeypatch
):
    user, _ = seeded_user
    _force_due(db_session, user.id, {"a": (2, 5.0), "b": (3, 5.0), "c": (4, 5.0)})
    before = auth_client.get("/api/v1/reviews/due").json()["items"]

    review = service.start_review(
        db_session, user_id=user.id, problem_id=_first_problem_id(db_session, user.id)
    )

    from app.repositories import reviews as reviews_repo

    def boom(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(reviews_repo, "upsert_memory", boom)
    with pytest.raises(RuntimeError):
        service.complete_review(
            db_session,
            user_id=user.id,
            session_id=review.id,
            outcome="good",
            independent=True,
            help_level=None,
            duration_seconds=None,
            notes=None,
        )
    monkeypatch.undo()
    db_session.rollback()
    db_session.expire_all()

    after = auth_client.get("/api/v1/reviews/due").json()["items"]
    assert after == before  # ranking and memory history unchanged


def _first_problem_id(db_session, user_id):
    return (
        db_session.query(UserProblem)
        .filter_by(user_id=user_id)
        .order_by(UserProblem.created_at)
        .first()
        .problem_id
    )


def test_upcoming_mode_is_separate_and_clearly_typed(
    auth_client, db_session, seeded_user
):
    user, _ = seeded_user
    _force_due(db_session, user.id, {"a": (2, 5.0), "b": (3, 5.0), "c": (4, 5.0)})
    # Push one item into the future.
    memories = db_session.query(MemoryState).filter_by(user_id=user.id).all()
    memories[0].due_at = datetime.now(UTC) + timedelta(hours=5)
    db_session.commit()
    db_session.expire_all()

    due = auth_client.get("/api/v1/reviews/due").json()
    assert all(i["status"] in ("due", "overdue") for i in due["items"])
    assert len(due["items"]) == 2

    upcoming = auth_client.get("/api/v1/reviews/due?mode=upcoming").json()
    assert upcoming["mode"] == "upcoming"
    assert len(upcoming["items"]) == 1
    item = upcoming["items"][0]
    assert item["status"] == "upcoming"
    assert 0 < item["seconds_until_due"] <= 5 * 3600
    assert item["priority_tier"] is None
    assert "Scheduled in" in item["priority_reason"]


def test_invalid_mode_rejected(auth_client, seeded_user):
    resp = auth_client.get("/api/v1/reviews/due?mode=someday")
    assert resp.status_code == 422
