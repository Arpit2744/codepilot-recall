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

### Activity aggregation (revision `0003`, Phase 2)

No `daily_activity` table: dashboard aggregates are **derived on read**
(ADR-0005) — timezone-correct bucketing depends on the queried zone, and the
unique constraints on `submissions`/`user_problems` make derived counts exact
by construction (repeated syncs cannot inflate them; discovering older
solves moves `first_solved_at` earlier and the aggregates follow). Revision
`0003` adds the indexes the scans need:
`submissions(cf_account_id, submitted_at)` and
`user_problems(user_id, first_solved_at)`.

### User sessions (revision `0005`, Phase 5)

- **user_sessions** — server-side session store: `user_id` FK CASCADE,
  UNIQUE `token_hash` (sha256 of a 256-bit opaque token; the raw token only
  ever lives in the HttpOnly cookie), `csrf_token_hash`,
  `issued_at`/`last_seen_at`/`expires_at`/`revoked_at`, minimal
  `created_via`. Indexes: unique token lookup, (`user_id`, `revoked_at`)
  for revoke-all, `expires_at` for cleanup.
- The same migration moves `cf_accounts` from a global
  `UNIQUE(handle_lower)` to `UNIQUE(user_id, handle_lower)` — handles are
  shareable public data (ADR-0009). Existing rows and history are
  preserved; dev-era users keep their data and can never log in.

### Review tables (revision `0004`, Phase 3)

- **review_sessions** — one review attempt per row: `user_id` + `user_problem_id`
  FKs (CASCADE), `started_at`/`completed_at` UTC, `status` pending/completed,
  `outcome` (again/hard/good/easy), `independent`, `help_level`
  (none/hint/editorial), optional `duration_seconds`/`notes`; index
  (`user_id`, `completed_at`) drives the Reviews heatmap (completed only).
- **memory_states** — UNIQUE `user_problem_id`: full serialized FSRS state
  (`{"version","scheduler","card","last_log"}`), `scheduler_version`,
  queryable `due_at` (indexed), `last_review_at`, `stability`, `difficulty`,
  `repetitions`, `lapses`. Corrupt state refuses to load (ADR-0006) — never
  silently reset.

## Not yet in the schema

`user_settings` / `notification_preferences` have no migration yet (planned
for post-beta). Everything described above is implemented and covered by
migrations `0001`–`0005`.

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
