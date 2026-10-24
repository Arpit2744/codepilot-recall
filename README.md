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
py -3.11 -m venv .venv                       # or python3 -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"   # Windows Git Bash
# source .venv/bin/activate && pip install -e ".[dev]"   # macOS/Linux
.venv/Scripts/python -m pytest
.venv/Scripts/python -m uvicorn app.main:app --reload
```

The API defaults to `postgresql+psycopg://...@localhost:5432`; tests run on
SQLite automatically. The worker is analogous in `services/worker`
(`celery -A worker.celery_app worker --loglevel=info`; add `--pool=solo` on
Windows hosts — prefer Docker instead).

Frontend: `npm install` at the repo root (workspace install,
Node **>= 22.22.2**, 24 recommended), then `npm run web:dev`.

## Verification status (updated 2026-10-24; Windows 10, Python 3.11.6, Node 24.22.1)

| Check                                   | Result                              |
| --------------------------------------- | ----------------------------------- |
| API `pytest` (11 tests)                 | **PASS** — 11 passed                |
| API `ruff check`                        | **PASS**                            |
| Worker `pytest` (3 tests)               | **PASS** — 3 passed                 |
| Worker `ruff check`                     | **PASS**                            |
| Alembic `upgrade head` → `check` → `downgrade base` (SQLite) | **PASS** — no drift |
| Live Uvicorn smoke test (`/health`, `/health/ready`, `/api/v1/`, 404 envelope, OpenAPI) | **PASS** |
| Web `npm install` (lockfile generated)  | **PASS**                            |
| Web `eslint` (next/core-web-vitals)     | **PASS**                            |
| Web `vitest` (5 tests)                  | **PASS** — 5 passed                 |
| Web `next build`                        | **PASS** — static prerender OK      |
| Playwright e2e (Chromium)               | **PASS** — 2 passed                 |
| Docker Compose startup                  | **NOT RUN** — no Docker on authoring machine |
| CI pipeline (GitHub Actions)            | **NOT RUN** — no remote configured  |

Known issues:

- Starlette emits a deprecation warning about `httpx` vs `httpx2` in
  TestClient; cosmetic, tracked for a later dependency refresh.

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
