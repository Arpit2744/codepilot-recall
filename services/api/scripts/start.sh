#!/bin/sh
set -eu

# CodePilot Recall API startup (Phase 6).
#
# Alembic migrations run first and gate uvicorn: if they fail, the script
# exits non-zero and the service never comes up half-migrated. Neon DDL
# should bypass PgBouncer, so DIRECT_DATABASE_URL is used for migrations
# only — the API process keeps its runtime DATABASE_URL.

if [ -n "${DIRECT_DATABASE_URL:-}" ]; then
  echo "[start] running migrations with DIRECT_DATABASE_URL"
  DATABASE_URL="$DIRECT_DATABASE_URL" alembic upgrade head
else
  echo "[start] DIRECT_DATABASE_URL not set; migrating with DATABASE_URL"
  alembic upgrade head
fi

echo "[start] migrations ok; starting uvicorn on port ${PORT:-8000}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
