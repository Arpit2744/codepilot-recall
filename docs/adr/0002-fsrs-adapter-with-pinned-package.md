# ADR-0002: FSRS via adapter over the pinned `fsrs` package

Date: 2026-10-24 · Status: accepted

## Context

Revision scheduling must implement the FSRS spaced-repetition model
(per-problem difficulty/stability, retrievability, adaptive intervals).
Reimplementing the algorithm from scratch is error-prone and unmaintainable.

## Decision

Use the maintained `fsrs` PyPI package — availability verified on PyPI;
**pin `fsrs==6.3.2` when Phase 3 begins** (not yet installed in Phase 0).
All usage goes through an internal adapter at `app/integrations/fsrs/`:

- UI outcomes map to FSRS ratings in one documented, easily revisable place
  (Again/Hard/Good/Easy; editorial-assisted attempts are recorded as
  non-independent).
- The adapter persists scheduler state + `scheduler_version` in
  `memory_states`, so a future package upgrade can migrate stored state.
- The product's **queue urgency layer** (due/overdue ordering, risk labels)
  stays separate from FSRS scheduling math and never mutates FSRS state.

## Consequences

- Scheduler upgrades are adapter-scoped changes with serialized-state
  versioning, not cross-cutting rewrites.
- Retrievability is surfaced only when the scheduler has enough state, always
  labeled a model estimate; the product never claims to know when a user
  will forget something.
