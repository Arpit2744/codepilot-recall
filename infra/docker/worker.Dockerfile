# Worker service image. Build context: repository root.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

COPY services/worker/pyproject.toml ./
COPY services/worker/worker ./worker

RUN pip install .

RUN useradd --create-home --shell /usr/sbin/nologin codepilot \
    && chown -R codepilot:codepilot /srv
USER codepilot

CMD ["celery", "-A", "worker.celery_app", "worker", "--loglevel=info"]
