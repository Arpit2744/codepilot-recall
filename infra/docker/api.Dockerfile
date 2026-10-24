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

RUN pip install .

RUN useradd --create-home --shell /usr/sbin/nologin codepilot \
    && chown -R codepilot:codepilot /srv
USER codepilot

EXPOSE 8000

# Migrations run in docker-compose command so image stays generic.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
