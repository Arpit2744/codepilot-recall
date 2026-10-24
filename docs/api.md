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

## Implemented (Phase 0 + Phase 1)

| Method | Path             | Description                                  |
| ------ | ---------------- | -------------------------------------------- |
| GET    | `/health`        | Liveness: process up; no external calls      |
| GET    | `/health/ready`  | Readiness: answers `SELECT 1` on the DB      |
| GET    | `/api/v1/`       | API metadata (name, version, status)         |
| POST   | `/api/v1/codeforces/accounts` | Link a handle; 202 + historical job queued (validation happens in the job) |
| GET    | `/api/v1/codeforces/accounts` | List the caller's accounts |
| POST   | `/api/v1/codeforces/accounts/{account_id}/sync` | Queue an incremental sync; returns the active job if one exists (`already_active`) |
| GET    | `/api/v1/codeforces/accounts/{account_id}/sync-status` | Account summary, latest jobs, totals |
| GET    | `/api/v1/dashboard/summary?timezone=` | Totals (submissions, solved problems), current streak, 5 recent first solves, account sync status |
| GET    | `/api/v1/dashboard/heatmap?from&to&timezone&mode` | Continuous local dates incl. zero days; `mode` ∈ submissions / first_solves / reviews |
| GET    | `/api/v1/problems` | Solved problems, paginated; filters `search`, `rating_min/max`, `tag`; sort ∈ first_solved_at / last_solved_at / name / rating / accepted_count, `order` asc/desc |
| POST   | `/api/v1/dev/users` | DEV ONLY (non-production): bootstrap a dev user for the `X-User-Id` boundary |

Dashboard semantics (ADR-0005): activity is derived on read from canonical
records; local dates bucket by the requested IANA timezone's midnight (never
UTC-relabeled); ranges are capped at 731 days. The `reviews` heatmap mode
returns `available: false` with an explanatory message until Phase 3 — review
data is never fabricated as zeros.

Phase 1 auth note: until Phase 5 ships real sessions, non-production requests
identify the user via the `X-User-Id` header (see ADR-0004); production
rejects user-data endpoints with 401. Cross-user access returns 404.

`GET /health` response:

```json
{"status": "ok", "service": "api", "version": "0.1.0", "environment": "local"}
```

## Planned endpoints

**Auth (Phase 5):** `POST /auth/register`, `POST /auth/login`, `GET /me` — replaces the dev header.

**Codeforces (Phase 1 additions later):** periodic reconciliation job type (`reconcile`)

**Dashboard (Phase 2):** `GET /dashboard/summary`, `GET /dashboard/heatmap?from=YYYY-MM-DD&to=YYYY-MM-DD`

**Problems (Phase 2):** `GET /problems/{problem_id}`, richer filters (rating, tag)

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
