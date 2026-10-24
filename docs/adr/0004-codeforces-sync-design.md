# ADR-0004: Codeforces sync runs only in the worker; dev-header auth interim

Date: 2026-10-24 · Status: accepted

## Context

Phase 1 adds Codeforces ingestion. Two forces shaped the design: the upstream
API rate limit (~1 request / 2 s) must be respected by the whole system, and
real authentication does not exist until Phase 5 — yet user isolation must be
enforceable and testable today.

## Decisions

1. **All Codeforces network calls execute in the Celery worker.** The API
   layer only persists a pending `sync_jobs` row and enqueues. One process
   class holds the shared Redis rate-limit gate, so concurrent syncs cannot
   multiply request pressure. `POST /codeforces/accounts` therefore answers
   202 and handle validation (user.info) happens inside the job — validation
   failures surface through `sync-status` rather than synchronously.
2. **Idempotent page-local commits.** Problem/submission upserts commit per
   page; the account cursor and job success commit only after the final page
   in one transaction. An interrupted import leaves verified data and no
   cursor — retrying is cheap and safe, and partial imports are never marked
   complete.
3. **Incremental stop by known-page detection.** `user.status` returns newest
   first; the importer stops when a fetched page contributes zero new
   submissions (that page is itself the verdict-refresh overlap). Submission
   IDs order nothing; `creationTimeSeconds` is the only time source.
4. **first_solved_at min-semantics.** Recomputed from accepted submissions;
   it can only move earlier as older data appears. Later submissions,
   resubmissions, and (future) revisions never overwrite it.
5. **Development auth boundary.** `get_current_user_id` resolves the user
   from `X-User-Id` in non-production environments only; production rejects
   every request with 401 until Phase 5 ships real sessions. All queries are
   owner-scoped in the repository layer regardless. A `POST /dev/users`
   bootstrap exists only outside production to materialize a dev user.
6. **Worker imports the API package.** `services/worker` installs
   `services/api` before itself (local, CI, Docker) so models, repositories,
   importer, and the CF client have exactly one implementation. A `file:`
   path dependency in pyproject was tried and rejected — pip's vendored
   packaging rejects the URL on older versions.

## Consequences

- Rate limiting is system-wide and testable (in-memory limiter for tests).
- The dev header is explicitly NOT authentication; deploying this API with
  `ENVIRONMENT=production` safely refuses all user-data endpoints.
- Adding another consumer of CF data (e.g. user.rating in a later phase)
  must go through the same client and limiter.
