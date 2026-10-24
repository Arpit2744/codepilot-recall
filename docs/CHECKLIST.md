# Build Checklist

Phased plan with exit criteria. A phase is complete only when its checks
**actually ran** and passed — file generation alone never counts.

## PHASE 0 — Foundation ✅ (code complete; environment-limited verification)

- [x] Inspect workspace (was empty), tools, runtime, git status
- [x] Monorepo skeleton: `apps/web`, `services/api`, `services/worker`,
      `packages/contracts`, `infra/docker`, `docs`, `migrations` (under
      `services/api/alembic`), CI
- [x] Dependency pins verified against registries (PyPI resolve + npm
      peerDependencies/engines audit); Python lockfiles committed
- [x] FastAPI app: health/ready endpoints, `/api/v1` router, JSON logging,
      CORS, error envelope, Pydantic settings
- [x] SQLAlchemy 2 models + Alembic env + revision `0001` (users)
- [x] Celery worker + beat skeleton with health task
- [x] Next.js app skeleton: landing page, API status component, Vitest +
      Playwright configs
- [x] Docker Compose (postgres/redis/api/worker/beat/web) + Dockerfiles + `.dockerignore`
- [x] GitHub Actions CI (api/worker/web/compose jobs)
- [x] Docs: architecture, database, api, testing, deployment, ADRs 1–3
- [x] **VERIFIED (2026-10-24, this machine)**: API pytest 11/11 PASS · worker
      pytest 3/3 PASS · ruff PASS (both) · alembic upgrade/check/downgrade
      PASS · live Uvicorn smoke test PASS · web `npm install` + eslint +
      vitest 5/5 + `next build` PASS · Playwright e2e 2/2 PASS (Chromium);
      `package-lock.json` generated
- [ ] **BLOCKED (needs Docker)**: `docker compose up --build` startup test;
      first real CI run (needs a GitHub remote)

**Phase 0 exit** ("fresh checkout can start with documented commands, CI
passes") is **not yet fully met** — blocked on the Node/Docker items above,
not on code.

## PHASE 1 — Data ingestion ✅ (code complete; CI run pending push)

- [x] Codeforces client (`user.info`, `user.status`) — shared Redis rate
      limiter (2.5 s default), bounded retries with backoff + jitter,
      Retry-After honored, FAILED envelope never read as empty history
- [x] Canonical problem identity + normalization (verdicts, UTC timestamps
      from `creationTimeSeconds` only)
- [x] Tables: `cf_accounts`, `problems`, `submissions`, `user_problems`,
      `sync_jobs` (Alembic revision `0002`; drift guard green)
- [x] Historical import (paged) + incremental sync (known-page stop with
      verdict-refresh overlap) + stale-job recovery + due-account dispatcher
      on the existing beat interval
- [x] Idempotent upserts (unique account+source id); per-account locking
      (`FOR UPDATE`) + atomic job claim; cursor only set on full success
- [x] `first_solved_at` = earliest accepted submission, min-semantics
- [x] Endpoints: link handle / list accounts / trigger sync (duplicate-safe) /
      sync status + totals / solved problems (paginated); dev-auth boundary
      (ADR-0004) with cross-user 404 isolation
- [x] Frontend onboarding page: dev-session bootstrap, handle connect,
      polling sync status with progress/errors + retry, solved list; no
      fabricated data, API-down states everywhere
- [x] **VERIFIED LOCALLY (executed)**: API pytest 70/70 · worker pytest 9/9 ·
      ruff both · alembic upgrade/check/downgrade on SQLite · web eslint ·
      vitest 9/9 · `next build` · Playwright 4/4
- [ ] **PENDING (remote)**: GitHub Actions run — api job re-verifies on
      PostgreSQL 16, worker job now installs the API package, compose job
      now builds and smoke-tests the full stack on a Linux runner (local
      Docker impossible: virtualization disabled)

**Exit criteria status**: fixture import ✓, repeated-sync idempotency ✓,
retry-safety ✓ (all via executed tests); the PostgreSQL-backed run happens
in CI on push.

## PHASE 2 — Dashboard

- [ ] `daily_activity` rollups + summary/heatmap endpoints
- [ ] Dashboard cards, activity heatmap (3 modes), solved-problems table with
      filters/pagination, topic/rating filters
- [ ] Timezone-boundary tests; aggregate-vs-fixture tests

**Exit**: aggregates match fixtures; timezone boundary tests pass.

## PHASE 3 — FSRS

- [ ] Install + pin `fsrs==6.3.2`; adapter in `app/integrations/fsrs`
- [ ] `review_sessions` + `memory_states` tables (Alembic revision)
- [ ] Review-session lifecycle: start → outcome → atomic state update
- [ ] Outcome→rating mapping (documented, revisable); idempotent completion
- [ ] State-transition and due-date tests; restart/timezone/overdue tests

**Exit**: outcomes update scheduler state; duplicate completion rejected;
state survives restarts.

## PHASE 4 — Revision queue

- [ ] Due/overdue queue with urgency layer (separate from FSRS)
- [ ] Risk indicators + explanatory labels; queue refresh after completion

**Exit**: queue matches stored scheduler state; failures never corrupt
memory history.

## PHASE 5 — Multi-user hardening

- [ ] Auth (register/login/sessions, password hashing), CSRF, rate limits
- [ ] Handle linking policy + optional safe ownership verification
- [ ] Cross-user isolation tests; quotas; observability; backup/restore
      rehearsal; deployment config; e2e tests

**Exit**: second user onboards independently; all cross-user access tests
pass.

## PHASE 6 — Beta release

- [ ] Deploy to accessible environment; validate real Codeforces sync;
      document limitations

**Exit**: real user connects a handle, sees history, completes a review, and
finds the schedule persisted on return.
