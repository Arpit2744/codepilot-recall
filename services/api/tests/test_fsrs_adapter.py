"""FSRS adapter tests — deterministic (fuzzing disabled), no network.

Exact expectations pin fsrs==6.3.2 default-parameter behavior; they act as a
canary on package upgrades (guarded at runtime by scheduler_version).
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.integrations.fsrs import adapter

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)


def test_new_state_shape():
    state = adapter.new_state(NOW)
    assert state["version"] == adapter.SCHEDULER_VERSION
    assert "scheduler" in state and "card" in state
    view = adapter.card_view(state)
    assert view["stability"] is None  # a fresh memory has learned nothing


def test_four_outcomes_apply_and_map_to_ratings():
    ratings = []
    for outcome in adapter.VALID_OUTCOMES:
        state = adapter.apply_review(None, outcome, now=NOW)
        ratings.append(adapter.review_log_rating(state))
    assert ratings == [1, 2, 3, 4]  # Again, Hard, Good, Easy


def test_first_review_exact_scheduling_pinned():
    good = adapter.apply_review(None, "good", now=NOW, duration_seconds=120)
    view = adapter.card_view(good)
    # New card + Good: advance to learning step 2 (10 minutes), fuzz off.
    assert view["due_at"] == NOW + timedelta(minutes=10)
    assert view["stability"] == pytest.approx(2.3065)
    assert view["last_review_at"] == NOW

    again = adapter.apply_review(None, "again", now=NOW)
    view = adapter.card_view(again)
    # New card + Again: repeat learning step 1 (60 seconds), hardest difficulty.
    assert view["due_at"] == NOW + timedelta(seconds=60)
    assert view["difficulty"] == pytest.approx(6.4133)
    assert adapter.card_view(good)["difficulty"] < view["difficulty"]


def test_easy_graduates_to_long_interval():
    state = adapter.apply_review(None, "good", now=NOW)
    next_day = NOW + timedelta(days=1)
    state = adapter.apply_review(state, "easy", now=next_day)
    view = adapter.card_view(state)
    # Good then Easy: Review state, ~12-day interval at 0.9 retention.
    assert view["due_at"] == next_day + timedelta(days=12)
    assert view["stability"] == pytest.approx(11.687482913582336)
    fresh_good = adapter.card_view(adapter.apply_review(None, "good", now=next_day))
    assert view["due_at"] > fresh_good["due_at"]


def test_serialization_roundtrip_restores_identical_state():
    state = adapter.apply_review(None, "good", now=NOW)
    restored = adapter.apply_review(state, "good", now=NOW + timedelta(minutes=30))
    direct = adapter.apply_review(
        adapter.apply_review(None, "good", now=NOW), "good", now=NOW + timedelta(minutes=30)
    )
    assert adapter.card_view(restored) == adapter.card_view(direct)


def test_outcome_ordering_monotonic_intervals():
    dues = {}
    for outcome in ("again", "hard", "good", "easy"):
        view = adapter.card_view(adapter.apply_review(None, outcome, now=NOW))
        dues[outcome] = view["due_at"]
    assert dues["again"] <= dues["hard"] <= dues["good"] <= dues["easy"]


def test_invalid_outcome_rejected():
    with pytest.raises(ValueError, match="invalid outcome"):
        adapter.apply_review(None, "perfect", now=NOW)


@pytest.mark.parametrize(
    "corrupt",
    [
        "not-a-dict",
        {},
        {"version": "fsrs-0.0.1", "card": {}, "scheduler": {}},
        {"version": adapter.SCHEDULER_VERSION, "card": {"garbage": True}, "scheduler": {}},
        {"version": adapter.SCHEDULER_VERSION, "card": {}, "scheduler": {"warp": 9}},
    ],
)
def test_corrupt_or_unsupported_state_raises_never_resets(corrupt):
    with pytest.raises(adapter.MemoryStateCorrupt):
        adapter.apply_review(corrupt, "good", now=NOW)
    with pytest.raises(adapter.MemoryStateCorrupt):
        adapter.card_view(corrupt)


def test_scheduler_is_deterministic():
    a = adapter.card_view(adapter.apply_review(None, "good", now=NOW))["due_at"]
    b = adapter.card_view(adapter.apply_review(None, "good", now=NOW))["due_at"]
    assert a == b  # fuzzing disabled: identical inputs, identical schedule
