# CodePilot Recall

Remember every problem you've solved. CodePilot Recall connects to your
Codeforces handle, imports your submission history, preserves the date each
problem was **first accepted**, visualizes activity, and schedules adaptive
revision sessions with an FSRS-based spaced-repetition scheduler.

## Stack

| Layer    | Technology                                                        |
| -------- | ----------------------------------------------------------------- |
| Frontend | Next.js 16 (TypeScript, App Router), Tailwind CSS 4, Recharts, Vitest, Playwright |
| Backend  | Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2, Alembic, pytest |
| Worker   | Celery 5 + Redis 7.2                                             |
| Data     | PostgreSQL 16 (psycopg 3)                                         |
| Infra    | Docker Compose, GitHub Actions CI                                 |

All dependencies are pinned; Python lockfiles are committed
(`services/*/requirements.lock`). Shared API types live in
`packages/contracts` (type-only package).

## Quickstart (Docker — recommended)

Requires Docker with Compose:

```bash
cp .env.example .env
docker compose up --build
```

- Web: http://localhost:3000 · API: http://localhost:8000/docs
- `api` runs `alembic upgrade head` on boot; healthchecks order startup.

## Quickstart (backend only, no Docker)

```bash
cd services/api
py -3.11 -m venv .venv-clean               # this repo's Python 3.11 env
.venv-clean/Scripts/python -m pip install -e ".[dev]"     # Windows Git Bash
# source .venv-clean/bin/activate && pip install -e ".[dev]"   # macOS/Linux
.venv-clean/Scripts/python -m pytest
DATABASE_URL="sqlite+pysqlite:///./local.db" \
  .venv-clean/Scripts/python -m uvicorn app.main:app --reload
```

Worker (needs the API package first; Redis optional — without a broker,
created sync jobs stay pending until one appears):

```bash
cd services/worker
.venv/Scripts/python -m pip install -e ../api -e ".[dev]"
.venv/Scripts/python -m pytest
# with Redis running:
.venv/Scripts/python -m celery -A worker.celery_app worker --loglevel=info --pool=solo
.venv/Scripts/python -m celery -A worker.celery_app beat --loglevel=info
```

Frontend: `npm install` at the repo root (workspace install,
Node **>= 22.22.2**, 24 recommended), then `npm run web:dev`.

## Verification status (updated 2026-10-24, Phase 1 complete locally)

| Check                                   | Result                              |
| --------------------------------------- | ----------------------------------- |
| API `pytest` (70 tests: health, models, migrations, CF client, importer, endpoints) | **PASS** |
| API `ruff check`                        | **PASS**                            |
| Worker `pytest` (9 tests: config, eager sync task, dispatcher) | **PASS** |
| Worker `ruff check`                     | **PASS**                            |
| Alembic `upgrade head` → `check` → `downgrade` → `upgrade` (SQLite) | **PASS** — no drift |
| Web `eslint`                            | **PASS**                            |
| Web `vitest` (9 tests incl. onboarding flow) | **PASS**                       |
| Web `next build` (`/` + `/onboarding` static) | **PASS**                      |
| Playwright e2e (Chromium, 4 tests)      | **PASS**                            |
| API tests against PostgreSQL 16         | runs in CI (api job) — next push exercises Phase 1 code |
| Docker Compose build + smoke            | runs in CI on Linux runners (local Docker impossible: virtualization disabled) |
| Real Codeforces API calls               | **NOT RUN** in automated tests (fixtures only, by design); first live run is manual/Phase 6 |

Known issues:

- Dev auth boundary (ADR-0004): `X-User-Id` header in non-production;
  production returns 401 until Phase 5. Not an authentication mechanism.
- Starlette TestClient deprecation warning re `httpx`/`httpx2` — cosmetic.

## Repository layout

```
apps/web/            Next.js frontend
packages/contracts/  Shared TypeScript API types
services/api/        FastAPI service, Alembic migrations, tests
services/worker/     Celery worker + beat, tests
infra/docker/        Dockerfiles (build context = repo root)
docs/                architecture, database, api, testing, deployment, ADRs, CHECKLIST
.github/workflows/   CI
```

## Security notes

- No secrets in source; configuration via environment (`.env.example`).
- The product never asks for your Codeforces password — only public handles.
- Per-user data isolation is enforced server-side in every query (Phase 5
  hardening completes auth flows).
