# Architecture

CodePilot Recall is a **modular monolith with an independent background
worker** (ADR-0001): one API codebase, one Celery worker codebase, one
PostgreSQL database, one Redis — no microservices. Locally they run as
Docker Compose services; the free-tier production deployment (Phase 6) runs
the web and API as Render Free services, PostgreSQL as Neon Free, Redis as
Upstash Free, and the worker as a *bounded GitHub Actions window* instead of
an always-on process (see [deployment.md](deployment.md) and
[.github/workflows/sync.yml](../.github/workflows/sync.yml)).

## System overview

```
                 ┌───────────────────────────────────────────────┐
                 │                  Browser                      │
                 │   Next.js 16 app (apps/web, dark-mode-first)  │
                 │   relative /api/v1/* → same-origin proxy      │
                 └───────────────┬───────────────────────────────┘
                                 │ HTTPS + session cookie + CSRF header
                 ┌───────────────▼───────────────────────────────┐
                 │  Next.js route handlers (apps/web/app/api/v1) │
                 │  forward to API_SERVER_URL (server-only env)  │
                 └───────────────┬───────────────────────────────┘
                                 │ forwarded request + forwarded Origin
                 ┌───────────────▼───────────────────────────────┐
                 │        FastAPI API (services/api)             │
                 │  auth · codeforces · dashboard · problems ·   │
                 │  reviews · integrations/{codeforces,fsrs}     │
                 └──────┬───────────────────────────┬────────────┘
                        │ SQLAlchemy 2 (psycopg3,   │ Celery broker/backend
                        │ Neon pooled + direct)     │ (TLS, Upstash)
               ┌────────▼─────────┐      ┌──────────▼──────────┐
               │  PostgreSQL 16   │      │      Redis          │
               │  (Neon; source   │      │  (Upstash; queue,   │
               │   of truth, UTC) │      │   rate limiting)    │
               └────────▲─────────┘      └──────────▲──────────┘
                        │                           │
             ┌──────────┴───────────────────────────┴──────────┐
             │  Celery worker (services/worker)                │
             │  runs in bounded GitHub Actions windows         │
             │  (.github/workflows/sync.yml, every ~4 h)       │
             └──────────────────────┬──────────────────────────┘
                                    │ HTTPS (rate-limited)
                           ┌────────▼─────────┐
                           │  Codeforces API  │
                           │  user.info       │
                           │  user.status     │
                           └──────────────────┘
```

## Components

| Component   | Path              | Responsibility                                        |
| ----------- | ----------------- | ----------------------------------------------------- |
| Web         | `apps/web`        | Next.js 16 App Router, TypeScript, Tailwind 4, same-origin API proxy, custom CSS-grid heatmap |
| Contracts   | `packages/contracts` | Type-only shared API shapes (mirrors Pydantic schemas) |
| API         | `services/api`    | REST API, request handling, transactions, health       |
| Worker      | `services/worker` | Celery tasks: Codeforces sync (in production, run in bounded GitHub Actions windows) |
| Migrations  | `services/api/alembic` | All schema changes via Alembic revisions          |

## Key decisions

- **Modular monolith** (ADR-0001): phase-scoped modules inside one service;
  split only on demonstrated scaling needs.
- **FSRS behind an adapter** (ADR-0002): the `fsrs` PyPI package (pinned
  `6.3.2`, verified on PyPI) is wrapped by `app/integrations/fsrs` so the
  scheduler implementation can be swapped without touching domain code. The
  product's queue *urgency* layer stays separate from FSRS *scheduling*.
- **UTC storage, user-timezone bucketing** (ADR-0003): every event timestamp
  is timezone-aware UTC; calendar days for heatmaps are computed in the
  user's `users.timezone` (IANA name).
- **Server-authoritative scheduling**: clients never send FSRS state, due
  dates, or recall probabilities — only review outcomes.
- **Idempotent sync**: submissions upserted on `(cf_account_id, source
  submission id)`; sync jobs persist cursor state before being marked
  complete.
- **Portability for tests**: SQLAlchemy models use portable types
  (`sa.Uuid`, `sa.JSON`, timezone-aware `DateTime`) so tests run on SQLite
  locally and on PostgreSQL in CI/production, through the same engine factory.

## Repository layout

```
apps/web            Next.js frontend (npm workspace @codepilot/web)
packages/contracts  Type-only shared API contract types
services/api        FastAPI + SQLAlchemy + Alembic + pytest
services/worker     Celery worker + beat + pytest
infra/docker        Dockerfiles (build context = repo root)
docs                Architecture, database, API, testing, deployment, ADRs
.github/workflows   CI pipeline
```

## Phase status

See [CHECKLIST.md](CHECKLIST.md) for phase-by-phase exit criteria and the
current verification state.
