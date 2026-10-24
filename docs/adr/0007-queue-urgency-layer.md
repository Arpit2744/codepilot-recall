# ADR-0007: Queue urgency is a separate layer over FSRS scheduling

Date: 2026-10-25 · Status: accepted

## Context

Phase 4 adds a prioritized revision queue and recall-risk indicators. The
FSRS scheduler already owns `due_at` and the serialized card; ranking must
never rewrite either.

## Decisions

1. **Separation.** `app/services/queue.py` computes ranking/labels ONLY,
   from persisted facts (due time, elapsed time, stability, estimated
   retrievability). Nothing in the queue layer writes to `memory_states`;
   `GET /reviews/due` is a pure read (tested: identical rows before/after).
2. **Statuses and tiers (documented policy, tunable without migration).**
   - `due` — due_at arrived, still inside a 24 h grace window (tier 4).
   - `overdue` — ≥ 24 h past due (tier 3).
   - Tier 2 "High" — ≥ 7 days past due. Tier 1 "Critical" — ≥ 30 days.
   - `upcoming` — a SEPARATE mode (`?mode=upcoming`), clearly typed, never
     mixed into the due response.
   All thresholds live in `QueuePolicy` (frozen dataclass).
3. **Ordering** (deterministic): tier asc → most overdue first → weakest
   memory (lowest stability) first → canonical problem key as stable
   tiebreaker.
4. **Retrievability is the FSRS package's own estimate.**
   `Scheduler.get_card_retrievability(card, now)` (verified against the
   installed fsrs==6.3.2: pure query, monotonic decay). Exposed as
   `retrievability` — always labeled a MODEL ESTIMATE, distinct from
   observed recall (review outcomes). Null when no valid history exists.
   Risk bands on the estimate: high < 0.50, elevated < 0.80, low ≥ 0.80.
5. **Corrupt state on the read path** — the item still appears (its due
   date is fact) with `retrievability: null`, `risk: null`, and an
   explicit "estimate unavailable (stored state unreadable)" note. The
   write path (completion) still refuses corrupt state outright.
6. **Every priority_reason string is assembled only from those computed
   fields** (e.g., "Overdue by 8 days — High priority — estimated recall ≈
   42% (model estimate)") — the UI renders API text verbatim.

## Consequences

- Tuning a threshold or band is a one-line `QueuePolicy` change; no
  migration, no stored rewrites, no history invalidation.
- The UI never fabricates urgency or risk: badges, percentages, and
  reasons all come from the API response.
