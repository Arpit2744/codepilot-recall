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


## Phase 5: authentication operations

- **HTTPS/proxy:** terminate TLS at the proxy; the app must receive
  `X-Forwarded-Proto` only from a trusted proxy. **Rate-limit keys use the
  socket peer address, not `X-Forwarded-For`** — behind a proxy all
  browsers share one key unless you deploy a trusted-proxy-aware limiter;
  that change must be explicit, not default.
- **Cookies/CORS:** production serves `__Host-cpr_session` (Secure,
  HttpOnly, SameSite=Lax, Path=/, no Domain). `CORS_ORIGINS` must list the
  exact web origin(s); wildcard-with-credentials is never used.
- **Secrets:** no token-signing secret exists (opaque tokens + sha256 at
  rest); only the existing Postgres/Redis credentials and `ENVIRONMENT`.
- **Session storage/expiry:** sessions live in `user_sessions`
  (absolute 30d, inactivity 7d). Cleanup of expired/revoked rows can be a
  scheduled `DELETE WHERE expires_at < now() OR revoked_at < now() - 30d`.
- **Redis:** required in production for shared auth rate limiting. If
  Redis is down, register/login answer 503 (fail closed) by design.
- **Rate limits:** `RATE_LIMIT_REGISTER` (5/h/IP), `RATE_LIMIT_LOGIN_IP`
  and `RATE_LIMIT_LOGIN_EMAIL` (10/15m each) — `events:window_seconds`.
- **Migrations/startup:** the API container runs `alembic upgrade head`
  before serving; revision `0005` adds sessions + shared handles.
- **Log redaction:** structured JSON logs; auth audit events
  (registration/login/logout/revocation/rate-limit) include user ids and
  IPs only — never credentials, cookies, CSRF tokens, or hashes.
- **Backup/restore:** rehearsed in CI (job `backup-restore`):
  migrate → seed → `pg_dump -Fc` → restore into a fresh DB → verify schema
  version `0005` + representative rows. The dump never enters artifacts.

```bash
# Manual equivalents
docker compose exec postgres pg_dump -U codepilot -Fc codepilot > backup.dump
docker compose exec -T postgres psql -U codepilot -c 'CREATE DATABASE codepilot_restore'
cat backup.dump | docker compose exec -T postgres pg_restore -U codepilot -d codepilot_restore --no-owner
```


## Phase 6: zero-cost beta deployment (Render + Neon + Upstash + GitHub Actions)

Architecture: FastAPI and Next.js run as Render Free web services; Neon Free
PostgreSQL; Upstash Free Redis; the Celery worker/beat runs as a bounded
GitHub Actions window every ~4 hours (`sync.yml`) — same broker, same tasks,
same DB job lifecycle, no always-on paid service.

### Same-origin API proxy

The browser only calls the Next.js origin (`/api/v1/...`); route handlers in
`apps/web/app/api/v1/[...path]/route.ts` forward server-side to
`API_SERVER_URL`. Cold starts are handled: connection failures (request
never delivered) are retried for up to ~90 s across all methods — this is
what wakes a sleeping Render service safely, even for registrations; a
timeout on a mutation returns an honest 504 immediately so a delivered
request is never replayed into a duplicate (GET/HEAD may retry). Session cookies are therefore first-party (HttpOnly,
SameSite=Lax, `__Host-` prefix in production), and FastAPI still validates
sessions, CSRF tokens, and the forwarded Origin against `CORS_ORIGINS`.
`NEXT_PUBLIC_API_BASE_URL` must stay EMPTY in deployment.

### Provider environment variables

Render **API** service: `ENVIRONMENT=production`, `DATABASE_URL` (Neon pooled
URL **pasted as-is**), `DIRECT_DATABASE_URL` (Neon direct URL, used by the
start command's `alembic upgrade head`), `REDIS_URL` (Upstash `rediss://`),
`CORS_ORIGINS` (the web origin), raised `RATE_LIMIT_*` (all browsers share
one proxy IP; per-IP granularity requires a future trusted-proxy change),
`BETA_ALLOWED_EMAILS` (invite gate; empty = open). Start command:
`sh -c "DATABASE_URL=$DIRECT_DATABASE_URL alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT"`.

Render **web** service: `API_SERVER_URL` (API origin), and
`NEXT_PUBLIC_API_BASE_URL` left empty/absent (must NOT be baked as a
localhost or cross-origin URL).

GitHub Actions secrets: `NEON_DIRECT_DATABASE_URL`,
`NEON_POOLED_DATABASE_URL`, `UPSTASH_REDIS_URL`; variable
`CF_SYNC_INTERVAL_MINUTES=240`.

### Scheduled sync window

`sync.yml` runs every ~4 hours (and on demand via "Run workflow"): migrate →
dispatch due syncs (replaces beat) → bounded 12-minute `celery worker
--pool=solo`. Interruption is safe: acks-late requeues unfinished tasks.
UI-triggered syncs execute at the next window; scheduled runs can also be
delayed by GitHub queueing — run the workflow manually when needed.

### Connection-string compatibility (Neon)

Neon issues `postgresql://` URLs; the installed driver is psycopg 3. Paste
Neon's pooled and direct URLs **as-is** — `app/core/database_url.py`
normalizes them at settings load (API startup, Alembic via settings, worker,
GitHub Actions):

- `postgres://` / `postgresql://` → `postgresql+psycopg://`
- `*.neon.tech` hosts get `sslmode=require` appended **only when absent**;
  existing query parameters (e.g. `options=project%3D...`) are preserved
- credentials/host/database are never rebuilt; non-PostgreSQL URLs
  (SQLite in tests) pass through untouched
