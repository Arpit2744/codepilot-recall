# Architecture

CodePilot Recall is a **modular monolith with an independent background worker**
(ADR-0001). One deployable API process, one worker (+ beat), one PostgreSQL
database, one Redis — no microservices.

## System overview

```
                    ┌──────────────────────────────────────────────┐
                    │                 Browser                      │
                    │  Next.js 16 app (apps/web, dark-mode-first)  │
                    └───────────────┬──────────────────────────────┘
                                    │ HTTPS / JSON (REST, /api/v1)
                    ┌───────────────▼──────────────────────────────┐
                    │        FastAPI API (services/api)            │
                    │  auth · dashboard · problems · reviews ·     │
                    │  analytics · settings                        │
                    │  app/integrations/{codeforces,fsrs}          │
                    └──────┬───────────────────────────┬───────────┘
                           │ SQLAlchemy 2 (psycopg3)   │ Celery broker/backend
                  ┌────────▼─────────┐        ┌────────▼─────────┐
                  │   PostgreSQL 16  │        │     Redis 7.2    │
                  │  (source of      │        │  (job queue,     │
                  │   truth, UTC)    │        │   rate limiting) │
                  └────────▲─────────┘        └────────▲─────────┘
                           │                           │
                    ┌──────┴───────────────────────────┴───────────┐
                    │  Celery worker + beat (services/worker)      │
                    │  Codeforces sync jobs · FSRS scheduling      │
                    └──────────────────────────────────────────────┘
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
| Web         | `apps/web`        | Next.js 16 App Router, TypeScript, Tailwind 4, Recharts |
| Contracts   | `packages/contracts` | Type-only shared API shapes (mirrors Pydantic schemas) |
| API         | `services/api`    | REST API, request handling, transactions, health       |
| Worker      | `services/worker` | Celery tasks: Codeforces sync, scheduling              |
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
