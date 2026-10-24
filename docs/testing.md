# Testing Strategy

## Commands

| Scope   | Command (from service dir)     | Covers                        |
| ------- | ------------------------------ | ----------------------------- |
| API     | `python -m pytest`             | unit + DB + migration tests   |
| API     | `python -m ruff check .`       | lint                          |
| Worker  | `python -m pytest`             | config + eager task execution |
| Web (auth E2E) | `npx playwright test -c playwright.auth.config.ts` (apps/web; real API on :8000 required) | register/login/logout/two-user isolation |
| Worker  | `python -m ruff check .`       | lint                          |
| Web     | `npm run test` (apps/web)      | Vitest unit/component tests   |
| Web     | `npm run lint`                 | ESLint (next/core-web-vitals) |
| Web     | `npm run e2e`                  | Playwright browser tests      |
| All     | `docker compose config -q`     | compose file validation       |

Run Python tests inside each service's venv (see README quickstart).

## Design

- **One engine path**: tests exercise the same `create_db_engine()` factory
  production uses. Locally the URL is SQLite (in-memory, StaticPool); CI runs
  the identical suite against a real PostgreSQL 16 service container.
- **Migration tests**: `tests/test_migrations.py` runs `alembic upgrade head`
  on a fresh file-backed database, compares produced tables against
  `Base.metadata` (drift guard), and downgrades to base.
- **Worker tests**: Celery runs with `task_always_eager` so no broker is
  needed; configuration assertions cover serialization and reliability flags.
- **Frontend**: Vitest + jsdom + Testing Library for components; `fetch` is
  stubbed per test (loading / ok / error states). Playwright covers the
  onboarding-critical flows against a dev server.
- **Alembic drift**: `alembic check` (after `upgrade head`) fails CI if
  models and migrations diverge.

## Planned coverage by phase

- Phase 1: Codeforces client against recorded fixtures (verdicts, pagination,
  retries, timestamp conversion), idempotent re-import, dedup constraints.
- Phase 2: aggregation correctness against known fixtures; timezone boundary
  tests for heatmap days.
- Phase 3: FSRS adapter state transitions, due dates, atomic review writes,
  duplicate-completion rejection.
- Phase 5: cross-user authorization tests, Docker Compose startup test,
  backup/restore rehearsal.
