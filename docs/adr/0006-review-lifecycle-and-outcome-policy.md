# ADR-0006: Review lifecycle, FSRS state persistence, and outcome policy

Date: 2026-10-24 · Status: accepted

## Context

Phase 3 adds the actual spaced-repetition engine: explicit review sessions
whose outcomes drive FSRS scheduling. Two prior decisions constrain it:
the Codeforces acceptance is evidence of a solve, not of recall (Phase 1),
and all user data is owner-scoped.

## Decisions

1. **fsrs==6.3.2 behind `app/integrations/fsrs/adapter.py`.** The package
   API was introspected from the installed wheel (Scheduler.review_card,
   Card/ReviewLog/Scheduler to_dict/from_dict) — never guessed. The adapter
   disables fuzzing for deterministic scheduling, pins
   `SCHEDULER_VERSION = "fsrs-6.3.2"`, and serializes
   `{"version", "scheduler", "card", "last_log"}` into
   `memory_states.scheduler_state` so any state reconstructs exactly across
   restarts; version upgrades migrate deliberately. Corrupt/unsupported
   state raises — it is NEVER silently reset.
2. **Two-step lifecycle.** `POST /reviews/sessions` creates a pending
   session against a solved problem; `POST .../complete` records the
   outcome and advances the scheduler. Completion takes a row lock
   (`FOR UPDATE` on PostgreSQL), so concurrent/duplicate completions
   serialize; the loser sees 409 and FSRS advances exactly once. The
   review row and the memory-state row commit in ONE transaction — any
   failure leaves both unchanged.
3. **Outcome policy (revisable without losing history).**
   - **Again** — forgot / could not solve without substantial help.
   - **Hard** — significant struggle or limited assistance.
   - **Good** — solved independently with reasonable effort.
   - **Easy** — solved independently, quickly, confidently.
   `independent` and `help_level` (none/hint/editorial) are recorded
   separately from the rating and never alter it. Only an independent
   Good/Easy sets `user_problems.independent_solve_verified`. Editorial
   use is therefore never counted as independent recall.
4. **The first review initializes the memory** (`apply_review(None, ...)`);
   a Codeforces OK verdict never creates FSRS history or a "successful
   recall". Due dates shown in the UI come only from the backend response
   after completion.

## Consequences

- Retrievability/queue urgency (Phase 4) reads the same serialized state.
- Upgrading fsrs requires a state-migration path (version-tagged) and will
  surface via the adapter's version guard, not silent drift.
- Heatmap "reviews" mode counts `review_sessions.completed_at` only —
  started-but-abandoned sessions never appear as activity.
