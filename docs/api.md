# API Reference (v1)

Base URL: `/api/v1` · Interactive docs: `/docs` (OpenAPI 3 auto-generated).

## Error envelope

Every error response uses one shape:

```json
{
  "error": {
    "code": "http_404",
    "message": "Not Found",
    "details": null
  }
}
```

## Implemented (Phase 0)

| Method | Path             | Description                                  |
| ------ | ---------------- | -------------------------------------------- |
| GET    | `/health`        | Liveness: process up; no external calls      |
| GET    | `/health/ready`  | Readiness: answers `SELECT 1` on the DB      |
| GET    | `/api/v1/`       | API metadata (name, version, status)         |

`GET /health` response:

```json
{"status": "ok", "service": "api", "version": "0.1.0", "environment": "local"}
```

## Planned endpoints

**Auth (Phase 5):** `POST /auth/register`, `POST /auth/login`, `GET /me`

**Codeforces (Phase 1):**
- `POST /codeforces/accounts` — link a handle (validates via `user.info`)
- `GET /codeforces/accounts` — list linked accounts + sync status
- `POST /codeforces/accounts/{account_id}/sync` — queue a sync job
- `GET /codeforces/accounts/{account_id}/sync-status` — job status

**Dashboard (Phase 2):** `GET /dashboard/summary`, `GET /dashboard/heatmap?from=YYYY-MM-DD&to=YYYY-MM-DD`

**Problems (Phase 2):** `GET /problems` (paginated, filters: rating, tag, solved-state), `GET /problems/{problem_id}`

**Reviews (Phases 3–4):**
- `GET /reviews/due` — server-computed queue (due + overdue, urgency order)
- `POST /reviews/sessions` — start a review session
- `POST /reviews/sessions/{session_id}/complete` — record outcome (idempotent; rejects duplicate completion)
- `GET /reviews/history`

**Analytics (Phase 2+):** `GET /analytics/topics`, `GET /analytics/retention`

**Settings (Phase 5):** `GET /settings`, `PATCH /settings`

## Rules

- All request/response bodies are validated Pydantic models.
- Clients are never authoritative for FSRS state, due dates, or recall
  probabilities — the server computes them.
- List endpoints paginate (`page`, `page_size`) and validate filters.
- Auth-required routes enforce per-user data isolation.
