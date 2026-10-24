"""FSRS adapter — the ONLY module that knows the fsrs package API.

Verified against fsrs==6.3.2 (installed; introspected, not assumed):
  Scheduler(parameters..., desired_retention=0.9, learning_steps=(1m, 10m),
            relearning_steps=(10m,), maximum_interval=36500, enable_fuzzing=True)
  Scheduler.review_card(card, rating, review_datetime, review_duration)
      -> (Card, ReviewLog)
  Card / ReviewLog / Scheduler each expose to_dict()/from_dict()/to_json()/...

Design:
- Fuzzing is DISABLED so identical inputs schedule identically (tests,
  reproducibility); the default FSRS parameters and steps are used.
- The full scheduler configuration + card + latest review log are serialized
  into `memory_states.scheduler_state`, tagged with SCHEDULER_VERSION, so a
  state can be reconstructed after restarts and migrated on upgrades.
- Corrupt/unsupported serialized state raises MemoryStateCorrupt — callers
  must surface it, never silently reset a user's scheduling history.
"""

from datetime import datetime
from typing import Any

from fsrs import Card, Rating, Scheduler

SCHEDULER_VERSION = "fsrs-6.3.2"

VALID_OUTCOMES = ("again", "hard", "good", "easy")

OUTCOME_TO_RATING: dict[str, Rating] = {
    "again": Rating.Again,
    "hard": Rating.Hard,
    "good": Rating.Good,
    "easy": Rating.Easy,
}


class MemoryStateCorrupt(Exception):
    """Serialized scheduler state cannot be restored; manual action needed."""


def make_scheduler() -> Scheduler:
    """Deterministic scheduler: default parameters, fuzzing off."""
    return Scheduler(enable_fuzzing=False)


def new_state(now: datetime) -> dict[str, Any]:
    """Serialized state for a fresh memory (no review history)."""
    scheduler = make_scheduler()
    card = Card()
    return {
        "version": SCHEDULER_VERSION,
        "scheduler": scheduler.to_dict(),
        "card": card.to_dict(),
    }


def _restore_card(state: dict[str, Any]) -> tuple[Scheduler, Card]:
    if not isinstance(state, dict) or "card" not in state:
        raise MemoryStateCorrupt("scheduler state is not a serialized FSRS state")
    version = state.get("version")
    if version != SCHEDULER_VERSION:
        raise MemoryStateCorrupt(
            f"state version {version!r} unsupported (expected {SCHEDULER_VERSION!r})"
        )
    try:
        scheduler = Scheduler.from_dict(state["scheduler"])
        card = Card.from_dict(state["card"])
    except Exception as exc:  # noqa: BLE001 — any parse failure is corruption
        raise MemoryStateCorrupt(f"cannot restore FSRS state: {exc}") from exc
    return scheduler, card


def apply_review(
    state: dict[str, Any] | None,
    outcome: str,
    *,
    now: datetime,
    duration_seconds: int | None = None,
) -> dict[str, Any]:
    """Apply one review outcome and return the updated serialized state.

    `state=None` initializes a fresh card first: a Codeforces acceptance is
    NOT a review — the first explicit review creates the memory.
    """
    if outcome not in VALID_OUTCOMES:
        raise ValueError(f"invalid outcome {outcome!r}; expected one of {VALID_OUTCOMES}")
    if state is None:
        state = new_state(now)
    scheduler, card = _restore_card(state)

    new_card, log = scheduler.review_card(
        card,
        OUTCOME_TO_RATING[outcome],
        review_datetime=now,
        review_duration=duration_seconds,
    )
    return {
        "version": SCHEDULER_VERSION,
        "scheduler": state["scheduler"],
        "card": new_card.to_dict(),
        "last_log": log.to_dict(),
    }


def card_view(state: dict[str, Any] | None) -> dict[str, Any]:
    """Query-friendly projection of a serialized state (no mutation)."""
    if state is None:
        return {
            "due_at": None,
            "last_review_at": None,
            "stability": None,
            "difficulty": None,
        }
    _, card = _restore_card(state)
    return {
        "due_at": card.due,
        "last_review_at": card.last_review,
        "stability": card.stability,
        "difficulty": card.difficulty,
    }


def retrievability(state: dict[str, Any] | None, *, at: datetime) -> float | None:
    """FSRS-model estimated recall probability in [0, 1] at time `at`.

    A MODEL ESTIMATE from the scheduler — not an observed fact, and no
    guarantee of forgetting. Returns None when no valid history exists
    (fresh/absent state). Pure query: never mutates the card or schedule.
    Corrupt/unsupported state raises MemoryStateCorrupt (never silently
    substituted with 0 or 1).
    """
    if state is None:
        return None
    scheduler, card = _restore_card(state)
    if card.last_review is None:
        return None  # no review history yet: nothing to estimate from
    return scheduler.get_card_retrievability(card, at)


def review_log_rating(state: dict[str, Any]) -> int | None:
    """Rating of the most recent applied review, if any (1=Again..4=Easy)."""
    log_dict = state.get("last_log") if isinstance(state, dict) else None
    if isinstance(log_dict, dict):
        return log_dict.get("rating")
    return None
