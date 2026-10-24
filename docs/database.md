# Database Design

PostgreSQL 16 is the source of truth. All changes go through Alembic
revisions (`services/api/alembic/versions/`). Event timestamps are
timezone-aware UTC (ADR-0003).

## Current schema

### users (revision `0001`)

| Column         | Type                    | Constraints                  |
| -------------- | ----------------------- | ---------------------------- |
| id             | UUID (PK)               | application-generated uuid4  |
| email          | VARCHAR(320)            | NOT NULL, unique index       |
| password_hash  | VARCHAR(255)            | NULL until Phase 5 auth      |
| display_name   | VARCHAR(64)             | NOT NULL                     |
| timezone       | VARCHAR(64)             | NOT NULL, default `'UTC'` (IANA name) |
| created_at     | TIMESTAMPTZ             | NOT NULL                     |
| updated_at     | TIMESTAMPTZ             | NOT NULL                     |

### Codeforces tables (revision `0002`, Phase 1)

- **cf_accounts** — `user_id` FK CASCADE, `handle` + globally-unique
  `handle_lower`, `verified_at`, `last_synced_at`, `sync_cursor` JSONB
  (`last_seen_submission_id`), `last_sync_error`.
- **problems** — shared across users; UNIQUE `canonical_key`
  (`{contestId}-{index}`, or `ps:{problemsetName}:{slug}` without a contest),
  name/rating/tags/url refresh freely, identity never changes.
- **submissions** — UNIQUE (`cf_account_id`, `cf_submission_id`);
  `submitted_at` from `creationTimeSeconds` (tz-aware UTC, immutable);
  verdict/counts refresh on re-sync; FK RESTRICT to problems.
- **user_problems** — UNIQUE (`user_id`, `problem_id`); `first_solved_at`
  (min-semantics: only moves earlier), `last_solved_at`, `accepted_count`,
  `independent_solve_verified` (Phase 3).
- **sync_jobs** — `job_type` (historical/incremental/reconcile), `status`
  (pending/running/succeeded/failed/cancelled), `attempt_count`,
  start/completion timestamps, `error_summary`, `progress` JSONB; index on
  (`cf_account_id`, `created_at`).

## Planned schema by phase

| Phase | Table            | Purpose                                                        |
| ----- | ---------------- | -------------------------------------------------------------- |
| 2     | `daily_activity` | per user/date rollup: submissions, first solves, reviews        |
| 3     | `review_sessions`| grade, hint level, duration, independent flag, idempotent completion |
| 3     | `memory_states`  | FSRS state per user_problem: difficulty, stability, retrievability, due_at, scheduler version |
| 5     | `user_settings` / `notification_preferences` | per-user options            |

## Invariants (enforced from Phase 1 onwards)

1. `first_solved_at` derives from the earliest known accepted submission and
   is **never** overwritten by a revision date.
2. Submission events stay separate from distinct solved problems
   (`submissions` vs `user_problems`).
3. Sync is idempotent: re-importing the same window creates no duplicates.
4. Review results and `memory_states` updates commit in one transaction.
5. Indexes on: due reviews (`memory_states.due_at`), account submission
   history, canonical problem lookup.
6. Every query filters by the owning `user_id` (authorization enforced
   server-side, never by client-supplied IDs alone).
7. `topic_mastery` is deferred until its semantics and evidence base are
   defined; Codeforces tags power topic analytics meanwhile.
