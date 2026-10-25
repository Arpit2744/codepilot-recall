# API service image. Build context: repository root.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

COPY services/api/pyproject.toml ./
COPY services/api/app ./app
COPY services/api/alembic ./alembic
COPY services/api/alembic.ini ./
COPY services/api/scripts/start.sh ./scripts/start.sh

RUN chmod +x scripts/start.sh && pip install .

RUN useradd --create-home --shell /usr/sbin/nologin codepilot \
    && chown -R codepilot:codepilot /srv
USER codepilot

EXPOSE 8000

# Start script: Alembic migrations first (DIRECT_DATABASE_URL when set —
# Neon DDL bypasses PgBouncer — else DATABASE_URL), then exec uvicorn on
# ${PORT:-8000}. JSON-array CMD: no shell parsing at exec time.
CMD ["/bin/sh", "scripts/start.sh"]
