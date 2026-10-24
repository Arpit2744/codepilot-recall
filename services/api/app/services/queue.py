"""Queue urgency layer — ranking and labels ONLY, never scheduling.

Separation of concerns (Phase 4): FSRS owns `due_at` and the serialized
card; this module computes queue position, status labels, and explanatory
reasons from already-persisted facts (due time, elapsed time, stability,
estimated retrievability). Nothing here mutates scheduler state.

All thresholds live in QueuePolicy so tuning never needs a migration.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True)
class QueuePolicy:
    # >= this far past due => status "overdue"; below it => "due" (arrived).
    overdue_after_seconds: int = 86_400  # 24h
    # Priority tiers by elapsed time past due (seconds).
    critical_after_seconds: int = 30 * 86_400  # tier 1: overdue >= 30d
    high_after_seconds: int = 7 * 86_400  # tier 2: overdue >= 7d
    # tier 3: status overdue (< 7d past due); tier 4: due (< 24h past due).
    # Risk bands on the FSRS retrievability ESTIMATE (model output).
    risk_high_below: float = 0.50
    risk_elevated_below: float = 0.80


QUEUE_POLICY = QueuePolicy()

TIER_LABELS = {1: "Critical", 2: "High", 3: "Overdue", 4: "Due"}

DAY = 86_400


def _as_aware(dt: datetime) -> datetime:
    """SQLite reloads timestamps naive; PostgreSQL keeps them aware."""
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def _humanize(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 3_600:
        return f"{max(1, seconds // 60)} minutes"
    if seconds < DAY:
        hours = round(seconds / 3_600)
        return f"{hours} hour{'s' if hours != 1 else ''}"
    days = round(seconds / DAY)
    return f"{days} day{'s' if days != 1 else ''}"


def risk_category(retrievability: float | None, policy: QueuePolicy = QUEUE_POLICY) -> str | None:
    """Band the retrievability ESTIMATE; None stays None (no history)."""
    if retrievability is None:
        return None
    if retrievability < policy.risk_high_below:
        return "high"
    if retrievability < policy.risk_elevated_below:
        return "elevated"
    return "low"


def classify_due(
    item: dict[str, Any], *, now: datetime, policy: QueuePolicy = QUEUE_POLICY
) -> dict:
    """Enrich one due/past-due item with status, tier, reason, and risk.

    `item` needs: due_at (aware), retrievability (float | None), stability
    (float | None). Retrievability may be None when no valid estimate
    exists (missing history OR unreadable state — callers pass None and may
    set `estimate_unavailable` to note the difference).
    """
    overdue_seconds = max(0.0, (now - _as_aware(item["due_at"])).total_seconds())
    is_overdue = overdue_seconds >= policy.overdue_after_seconds
    status = "overdue" if is_overdue else "due"

    if overdue_seconds >= policy.critical_after_seconds:
        tier = 1
    elif overdue_seconds >= policy.high_after_seconds:
        tier = 2
    elif is_overdue:
        tier = 3
    else:
        tier = 4

    risk = risk_category(item.get("retrievability"), policy)

    reason = _reason(
        overdue_seconds,
        tier,
        item.get("retrievability"),
        risk,
        item.get("estimate_unavailable", False),
    )
    return {
        "status": status,
        "overdue_seconds": int(overdue_seconds),
        "priority_tier": tier,
        "priority_reason": reason,
        "risk": risk,
    }


def _reason(
    overdue_seconds: float,
    tier: int,
    retrievability: float | None,
    risk: str | None,
    estimate_unavailable: bool,
) -> str:
    parts: list[str] = []
    if tier == 4:
        parts.append("Due now")
    else:
        parts.append(f"Overdue by {_humanize(overdue_seconds)}")
    if tier <= 2:
        parts.append(f"{TIER_LABELS[tier]} priority")
    if retrievability is not None:
        parts.append(f"estimated recall ≈ {retrievability:.0%} (model estimate)")
        if risk == "high":
            parts.append("low estimated retrievability")
    elif estimate_unavailable:
        parts.append("recall estimate unavailable")
    return " — ".join(parts)


def classify_upcoming(item: dict[str, Any], *, now: datetime) -> dict:
    """Future items are clearly typed as upcoming; never mixed into 'due'."""
    until = (_as_aware(item["due_at"]) - now).total_seconds()
    return {
        "status": "upcoming",
        "overdue_seconds": 0,
        "seconds_until_due": int(until),
        "priority_tier": None,
        "priority_reason": f"Scheduled in {_humanize(until)}",
        "risk": None,
    }


def order_due_queue(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deterministic order: tier, most overdue first, weakest memory first,
    then canonical problem key as the stable tiebreaker."""
    return sorted(
        items,
        key=lambda i: (
            i["priority_tier"],
            -i["overdue_seconds"],
            i["stability"] if i["stability"] is not None else float("inf"),
            i["canonical_key"],
        ),
    )


def order_upcoming_queue(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda i: (i["seconds_until_due"], i["canonical_key"]))
