# Deployment & Operations

## Local development (Docker)

```bash
cp .env.example .env
docker compose up --build
```

- Web: http://localhost:3000
- API: http://localhost:8000 (docs at `/docs`)
- PostgreSQL on `:5432`, Redis on `:6379` (both published for local tooling)

The `api` container runs `alembic upgrade head` before starting Uvicorn, so
schema is always current on boot. Healthchecks gate startup ordering
(`service_healthy` conditions).

## Local development (backend without Docker)

```bash
cd services/api
py -3.11 -m venv .venv          # or: python3 -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]"     # Windows
# source .venv/bin/activate && pip install -e ".[dev]"  # macOS/Linux
.venv/Scripts/python -m pytest
.venv/Scripts/python -m uvicorn app.main:app --reload
```

Worker analogously under `services/worker`
(`celery -A worker.celery_app worker --loglevel=info`; on Windows add
`--pool=solo` — Celery does not support prefork there; prefer Docker).

## Environment variables

See [.env.example](../.env.example). Everything configurable is environment
driven; no secrets live in source. `DATABASE_URL` uses the psycopg3 scheme
(`postgresql+psycopg://`).

## Health & monitoring

| Check            | Endpoint       | Meaning                          |
| ---------------- | -------------- | -------------------------------- |
| Liveness         | `/health`      | process up                       |
| Readiness        | `/health/ready`| DB answers `SELECT 1`            |
| Worker liveness  | `worker.health.ping` Celery task | broker round-trip |

Logs are structured JSON (one object per line) from both API and worker.

## Backup & restore (PostgreSQL)

```bash
# Backup
docker compose exec postgres pg_dump -U codepilot -Fc codepilot > backup_$(date +%F).dump

# Restore into a fresh volume
docker compose down
docker volume rm codepilot-recall_pgdata
docker compose up -d postgres
cat backup_2026-10-24.dump | docker compose exec -T postgres pg_restore -U codepilot -d codepilot --clean --if-exists
docker compose up -d
```

Rehearse this before real user data exists (Phase 5 exit criterion).

## CI (GitHub Actions)

`.github/workflows/ci.yml` runs on every push/PR:
- **api**: ruff + pytest against PostgreSQL 16 service container
- **worker**: ruff + pytest
- **web**: eslint + vitest + `next build` (Node 24)
- **compose**: `docker compose config` validation

## Production notes (Phase 6)

- Run API behind TLS with a reverse proxy; set `ENVIRONMENT=production`,
  real `CORS_ORIGINS`, and managed secrets.
- Scale workers with `docker compose up --scale worker=N` (Celery acks-late,
  prefetch 1 — safe for long sync jobs).
- Schedule `pg_dump` backups off-box; test restores.
