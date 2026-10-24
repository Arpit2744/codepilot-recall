# Build Checklist

Phased plan with exit criteria. A phase is complete only when its checks
**actually ran** and passed — file generation alone never counts.

## PHASE 0 — Foundation ✅ (verified: local suites then CI runs #1–#4 green)

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

## PHASE 1 — Data ingestion ✅ (complete, remotely verified)

CI run https://github.com/Arpit2744/codepilot-recall/actions/runs/40117225412
passed all four jobs at commit `3a5f64e` (2026-10-24): API tests on
PostgreSQL 16, worker tests, web lint/unit/build, and the Docker Compose
build & smoke (migrations ran, `/health/ready` healthy, web returned 200 on
a Linux runner). Live Codeforces calls were NOT part of verification — all
tests use fixtures by design; the first live import remains a manual/Phase 6
step.

- [x] Codeforces client (`user.info`, `user.status`) — shared Redis/in-memory rate limiter (2.5 s default), bounded retries with backoff + jitter, Retry-After honored, FAILED envelope never read as empty history
- [x] Canonical problem identity + normalization (verdicts, UTC timestamps from `creationTimeSeconds` only)
- [x] Tables: `cf_accounts`, `problems`, `submissions`, `user_problems`, `sync_jobs` (revision `0002`; drift guard green on SQLite and PostgreSQL)
- [x] Historical import (paged) + incremental sync (known-page stop with verdict-refresh overlap) + stale-job recovery + due-account dispatcher on beat
- [x] Idempotent upserts; per-account locking; cursor only set on full success; `first_solved_at` min-semantics
- [x] Endpoints + dev-auth boundary (ADR-0004) with cross-user 404 isolation
- [x] Frontend onboarding page; ADR-0004; docs; `.env.example` CF knobs
- [x] CI fixes verified by green runs: test-package imports, workspace-aware web image build, lockfile in build context, CORS `NoDecode` parsing, compose `--wait` + retried web probe

## PHASE 2 — Dashboard ✅ (complete, remotely verified)

CI run https://github.com/Arpit2744/codepilot-recall/actions/runs/40119818727
passed all four jobs at commit `9471173` (2026-10-24), including the API
suite with Phase 2 tests on PostgreSQL 16 and the Compose smoke.

- [x] Aggregation design: derive on read from canonical tables (ADR-0005 —
      no `daily_activity` materialization; timezone-dependent bucketing and
      idempotent sources make derivation exact by construction)
- [x] Migration `0003`: `submissions(cf_account_id, submitted_at)` +
      `user_problems(user_id, first_solved_at)` indexes; drift guard green
- [x] `GET /dashboard/summary?timezone=` — totals, streak, recent first
      solves, account sync status (existing data only)
- [x] `GET /dashboard/heatmap?from&to&timezone&mode` — continuous local
      dates incl. zeros; `reviews` mode honestly unavailable until Phase 3
- [x] `GET /problems` filters: search/rating range/exact tag; validated
      sort whitelist with deterministic tiebreaks (nulls last); pagination
- [x] `/dashboard` page: summary cards, 3-mode heatmap (Reviews disabled
      with explanation), filtered table, timezone selector, loading/empty/
      error/API-down states, no fabricated data
- [x] **VERIFIED LOCALLY (executed)**: API pytest **105/105** · worker
      pytest 9/9 · ruff both · alembic 0003 upgrade/check/downgrade on
      SQLite · eslint · vitest **16/16** · `next build` (`/dashboard`
      static) · Playwright **6/6**
- [x] Timezone-boundary tests: UTC-midnight submissions land on the correct
      local date for Asia/Kolkata (+5:30, next day) and America/New_York
      (−4, previous day); aggregates match fixtures; repeated syncs and
      older-solve discovery verified against endpoints
- [x] GitHub Actions run 40119818727 for `9471173`: all four jobs green
      (PostgreSQL-backed API tests + Compose smoke included)

**Exit criteria**: aggregates match fixtures ✓ (endpoint tests); timezone
boundary tests pass ✓. Remote CI run closes this phase.

## PHASE 3 — FSRS ✅ (complete, remotely verified)

CI run https://github.com/Arpit2744/codepilot-recall/actions/runs/40121991245
passed all four jobs at commit `22ffefc` (2026-10-24).

- [x] `fsrs==6.3.2` pinned (API introspected from the installed wheel);
      adapter in `app/integrations/fsrs` with fuzzing off, version-tagged
      serialized state, corrupt-state refusal (ADR-0006)
- [x] `review_sessions` + `memory_states` tables (revision `0004`;
      drift guard green on SQLite)
- [x] Lifecycle: POST sessions → POST complete; row-locked, atomic
      (review + memory in one transaction); repeat completion → 409,
      FSRS advanced exactly once
- [x] Outcome policy Again/Hard/Good/Easy documented (ADR-0006);
      independent + help_level recorded separately; independent Good/Easy
      sets `independent_solve_verified`; CF acceptance never a review
- [x] GET /reviews/due, /reviews/history; /review UI with honest states
      and backend-confirmed next due date; Reviews heatmap mode live on
      completed_at (timezone-bucketed)
- [x] **VERIFIED LOCALLY (executed)**: API pytest **137/137** (adapter
      pinned-value tests; lifecycle, four outcomes, independence,
      rollback-together, restart survival, corrupt-state refusal,
      duplicate completion, isolation, due/overdue, tz heatmap) · worker
      9/9 · ruff both · alembic 0004 upgrade/check/downgrade · eslint ·
      vitest 21/21 · `next build` · Playwright 8/8
- [x] GitHub Actions run 40121991245 for `22ffefc`: all four jobs green

**Exit criteria**: outcomes update scheduler state ✓; duplicate completion
rejected ✓; state survives restarts ✓; remote CI run closes the phase.

## PHASE 4 — Revision queue

- [ ] Due/overdue queue with urgency layer (separate from FSRS)
- [ ] Risk indicators + explanatory labels; queue refresh after completion

**Exit**: queue matches stored scheduler state; failures never corrupt
memory history.

## PHASE 5 — Authentication & hardening ✅ (complete, remotely verified)

CI run https://github.com/Arpit2744/codepilot-recall/actions/runs/40134570747
passed all six jobs at commit `7597d6c` (2026-10-25): API tests on
PostgreSQL 16, worker, web, Docker Compose smoke, **backup/restore
rehearsal** (real pg_dump → pg_restore → integrity verification), and
**integrated auth E2E** (real API + PostgreSQL + Playwright).

- [x] Argon2id via pinned `argon2-cffi==25.1.0` (API introspected,
      benchmarked ~120ms at m=64MiB/t=2/p=4; parameters in Settings) —
      ADR-0008. No plaintext/fast hashes; hashes never logged or returned.
- [x] `POST /auth/register|login|logout`, `GET /auth/me|csrf|sessions`,
      `POST /auth/sessions/revoke-all`. Email normalization + safe
      concurrent uniqueness (IntegrityError → 409); uniform login failure
      with timing-equalizing dummy verify (no enumeration).
- [x] Server-side sessions (migration `0005`): 256-bit opaque tokens,
      sha256-at-rest, absolute 30d + inactivity 7d, revocation timestamps,
      CSRF-token hash per session. Cookies HttpOnly/SameSite=Lax/Path=/;
      production adds Secure + `__Host-` prefix (fail closed).
- [x] CSRF synchronizer token on every mutation (`X-CSRF-Token`,
      compare_digest) + Origin/Referer validation; login/register covered
      by the origin policy. GET/HEAD never mutate.
- [x] `X-User-Id` identity REMOVED everywhere (dependency rewritten; dev
      bootstrap route deleted; frontend uses cookie sessions only).
      Dev-era users keep their data and can never log in (ADR-0008).
- [x] Shared Redis rate limiting (register/login IP + email) with
      fail-closed 503 in production, in-process fallback elsewhere;
      429 + Retry-After; trusted-proxy stance documented (socket peer IP).
- [x] Handle policy: public handles shareable across users (ADR-0009;
      migration to UNIQUE(user_id, handle_lower); concurrent-link test) +
      per-user linked-account quota (default 5).
- [x] Audit events (registration/login/logout/revocation/rate-limit) via
      structured JSON logs — no credentials/tokens.
- [x] Frontend: /login + /register, cookie bootstrap via /auth/me, logout,
      CSRF handled inside the shared fetch wrapper (auto-acquire + one
      rotate-retry), 401→login CTA, 409/429 surfaced safely; no bearer
      tokens in localStorage/URLs.
- [x] Backup/restore rehearsal scripts + CI job (`backup-restore`):
  migrate → seed → pg_dump → restore to fresh DB → verify schema `0005`
  and representative rows; dump kept out of artifacts.
- [x] Integrated auth E2E (CI job `e2e-auth` + local): register →
      onboarding → dashboard survives reload → logout invalidates; second
      user onboards independently with a shared handle and isolated data;
      wrong-password shows the uniform error.
- [x] **VERIFIED LOCALLY (executed)**: API pytest **190/190** (34 new
      auth-security tests: Argon2 verification, cookie flags, session
      expiry/inactivity/revocation/tamper, CSRF matrix incl. rotation +
      referer fallback + non-browser, rate limits incl. window reset +
      Redis-outage fail-closed/degrade, production `__Host-` cookie,
      enumeration parity, dev-bootstrap gone, handle sharing, quota) ·
      worker 9/9 · ruff both · alembic 0005 upgrade/drift/downgrade clean ·
      eslint · tsc · vitest **31/31** · `next build` · standard Playwright
      8/8 · integrated auth Playwright **3/3** against a live API
- [x] GitHub Actions run 40134570747 for `7597d6c`: all six jobs green,
      including backup/restore rehearsal and integrated auth E2E

**Exit criteria**: session auth replaces the dev header ✓ (no fallback
anywhere); cross-user isolation green across endpoints ✓; rate limits and
operational safeguards tested ✓; backup/restore rehearsed ✓ (verified in
CI); remote CI run green ✓ — phase closed. Not claimed: security audit,
email verification, password reset (documented as deferred).

## PHASE 6 — Beta release

- [ ] Deploy to accessible environment; validate real Codeforces sync;
      document limitations

**Exit**: real user connects a handle, sees history, completes a review, and
finds the schedule persisted on return.
