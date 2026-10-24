# Database Design

PostgreSQL 16 is the source of truth. All changes go through Alembic
revisions (`services/api/alembic/versions/`). Event timestamps are
timezone-aware UTC (ADR-0003).

## Current schema (Phase 0)

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

## Planned schema by phase

| Phase | Table            | Purpose                                                        |
| ----- | ---------------- | -------------------------------------------------------------- |
| 1     | `cf_accounts`    | handle link per user, sync cursor, `last_synced_at`, `last_sync_error`, unique ownership |
| 1     | `problems`       | canonical problem identity (contest_id + index + name), rating, tags, URL |
| 1     | `submissions`    | per-account source submissions; unique `(cf_account_id, cf_submission_id)` |
| 1     | `user_problems`  | first/last solve, accepted count, unique `(user_id, problem_id)` |
| 1     | `sync_jobs`      | job type/status/attempts/error summary                          |
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
