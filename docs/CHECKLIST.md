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

## PHASE 1 — Data ingestion (next)

- [ ] Codeforces client (`user.info`, `user.status`) with shared rate limiter,
      retries with backoff + jitter, upstream-error handling
- [ ] Canonical problem identity + normalization (verdicts, timestamps)
- [ ] Tables: `cf_accounts`, `problems`, `submissions`, `user_problems`, `sync_jobs`
      (Alembic revision)
- [ ] Historical import + incremental sync + periodic reconciliation
- [ ] Idempotent upserts; per-account locking; cursor persistence
- [ ] `first_solved_at` derivation from earliest accepted submission
- [ ] Mocked integration tests: accepted/rejected submissions, duplicates,
      pagination, failures, retries, timestamp conversion
- [ ] Sync job-status endpoint + manual sync trigger

**Exit**: fixture handle imports correctly; repeated syncs create no
duplicates; failures retry safely.

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
