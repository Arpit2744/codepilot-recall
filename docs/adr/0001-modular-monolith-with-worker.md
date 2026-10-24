# ADR-0001: Modular monolith with an independent background worker

Date: 2026-10-24 · Status: accepted

## Context

CodePilot Recall needs synchronous request handling (REST API, dashboards)
and long-running background jobs (Codeforces historical imports, periodic
sync, FSRS scheduling) with retry semantics.

## Decision

Deploy one FastAPI application and one Celery worker (+ beat) against shared
PostgreSQL and Redis. Domain code is organized in phase-scoped modules
(`models/`, `repositories/`, `services/`, `integrations/`) inside the single
API service.

## Consequences

- One codebase to test and deploy; transactions span request-scoped work.
- Codeforces rate limiting is enforced centrally in the worker via Redis.
- If sync load grows, the worker scales independently (`--scale worker=N`)
  without touching the API.
- Splitting into separate services remains possible later along the existing
  module boundaries; we defer that until a demonstrated need.
