# CodePilot Recall

Remember every problem you've solved. CodePilot Recall connects to your
Codeforces handle, imports your submission history, preserves the date each
problem was **first accepted**, visualizes activity, and schedules adaptive
revision sessions with an FSRS-based spaced-repetition scheduler.

## Stack

| Layer    | Technology                                                        |
| -------- | ----------------------------------------------------------------- |
| Frontend | Next.js 16 (TypeScript, App Router), Tailwind CSS 4, custom CSS-grid heatmap, Vitest, Playwright |
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
Node **>= 22.22.2**, 24 recommended), then `npm run web:dev`. The web app
proxies `/api/v1/*` to the API (`API_SERVER_URL`, default
`http://127.0.0.1:8000`) — no CORS setup needed locally.

## Verification status (updated 2026-10-25, Phase 6 deployed to production)

See [docs/learning-guide.md](docs/learning-guide.md) for a guided tour of
the whole codebase, and [docs/CHECKLIST.md](docs/CHECKLIST.md) for the
phase-by-phase verification record.

| Check                                   | Result                              |
| --------------------------------------- | ----------------------------------- |
| API `pytest` (190 tests: + Argon2 auth, sessions, CSRF, rate limits, handle sharing) | **PASS** |
| API `ruff check`                        | **PASS**                            |
| Worker `pytest` (9 tests)               | **PASS**                            |
| Worker `ruff check`                     | **PASS**                            |
| Alembic `0001→0003` upgrade → `check` → downgrade (SQLite) | **PASS** — no drift |
| Web `eslint`                            | **PASS**                            |
| Web `vitest` (31 tests incl. auth pages + session states) | **PASS**               |
| Web `next build` (`/`, `/onboarding`, `/dashboard` static) | **PASS**           |
| Playwright e2e (Chromium, 8 tests) + integrated auth E2E in CI (live API + PostgreSQL) | **PASS** |
| PostgreSQL 16 + Docker Compose smoke    | verified in CI: P1 40117225412, P2 40119818727, P3 40121991245, P4 40123762388, P5 40134570747, P6 40184329913 (`7e13a19`, all six jobs) |
| Live production deployment (Render Free ×2, Neon Free, Upstash Free) | deployed; API `/health/ready` verified by the repository owner |
| Real Codeforces history import + scheduled sync | completed for the owner's account in production (owner-verified, 2026-10-25) |
| Real Codeforces API calls               | **NOT RUN** in automated tests (fixtures only, by design); first live import is manual/Phase 6 |

Timezone-boundary tests: submissions near UTC midnight land on the correct
local date for Asia/Kolkata and America/New_York; heatmap aggregates match
fixtures; repeated syncs never inflate totals (ADR-0005 derives everything
from canonical records).

Known issues:

- Email verification and password reset are deferred (no mail provider;
  documented in ADR-0008) — not silently faked.
- No professional security audit or penetration test has been performed;
  green CI is necessary evidence, not proof of security.
- Sync reliability beyond the first successful scheduled run is still being
  observed (free-tier workers run in bounded GitHub Actions windows).
- Starlette TestClient deprecation warning re `httpx`/`httpx2` — cosmetic.

## Repository layout

```
apps/web/            Next.js frontend (same-origin /api/v1 proxy included)
packages/contracts/  Shared TypeScript API types
services/api/        FastAPI service, Alembic migrations, tests
services/worker/     Celery worker (locally via compose; in production a
                     bounded GitHub Actions window — see .github/workflows/sync.yml)
infra/docker/        Dockerfiles (build context = repo root)
docs/                architecture, database, api, testing, deployment, ADRs,
                     CHECKLIST, learning-guide
.github/workflows/   ci.yml (six jobs) + sync.yml (scheduled sync windows)
```

New to the codebase? Start with [docs/learning-guide.md](docs/learning-guide.md) —
a guided, lesson-by-lesson tour of the whole system.

## Security notes

- No secrets in source; configuration via environment (`.env.example`).
- The product never asks for your Codeforces password — only public handles.
- Per-user data isolation is enforced server-side in every query (Phase 5
  hardening completes auth flows).
