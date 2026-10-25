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
| POST   | `/api/v1/reviews/sessions` | Start a review for a solved `problem_id`; 201 with session + problem + memory (null before the first review) |
| GET    | `/api/v1/reviews/sessions/{id}` | Session status + problem + memory state |
| POST   | `/api/v1/reviews/sessions/{id}/complete` | Record outcome; advances FSRS exactly once; 409 on repeat completion |
| GET    | `/api/v1/reviews/due?mode=due\|upcoming&limit=` | Revision queue (see contract below) |
| GET    | `/api/v1/reviews/history` | Completed reviews, newest first, paginated |

Revision queue contract (ADR-0007): `mode=due` (default) returns items with
`due_at <= now`, urgency-ranked; `mode=upcoming` returns future items only,
clearly typed — never mixed into due. Each due item carries:

```json
{
  "problem": { "id": "…", "name": "Theatre Square", "url": "…", "…": "…" },
  "due_at": "2026-09-20T08:00:00Z",
  "status": "overdue",            // due | overdue (>=24h past due_at)
  "overdue_seconds": 3024000,
  "priority_tier": 1,             // 1 Critical >=30d, 2 High >=7d, 3 Overdue, 4 Due
  "priority_reason": "Overdue by 35 days — Critical priority — estimated recall ≈ 42% (model estimate) — low estimated retrievability",
  "retrievability": 0.42,         // FSRS MODEL ESTIMATE; null when no valid history
  "risk": "high",                 // high <0.50, elevated <0.80, low >=0.80; null with the estimate
  "stability": 4.2, "repetitions": 3, "lapses": 1, "last_review_at": "…"
}
```

Ordering: tier → most overdue → lowest stability → canonical key (stable
tiebreaker). Stored vs computed: `due_at`/`stability`/serialized FSRS state
are stored facts; `status`, `overdue_seconds`, tiers, reasons,
retrievability, and risk are computed on read and never persisted. The
layer never mutates scheduler state. Corrupt serialized state: the item
still appears with `retrievability: null` and an explicit
"estimate unavailable (stored state unreadable)" note; completing reviews
on corrupt state is refused (500, no reset — ADR-0006).

Review outcome policy (ADR-0006): **Again** = forgot / needed substantial
help; **Hard** = significant struggle or limited assistance; **Good** =
solved independently with effort; **Easy** = solved independently, quickly,
confidently. `independent` and `help_level` (none/hint/editorial) are
recorded separately from the rating; only independent Good/Easy marks a
solve as independently verified. A Codeforces acceptance is never an FSRS
review — the first explicit outcome initializes the memory. Heatmap
`reviews` mode counts completed sessions bucketed by the requested timezone.

Dashboard semantics (ADR-0005): activity is derived on read from canonical
records; local dates bucket by the requested IANA timezone's midnight (never
UTC-relabeled); ranges are capped at 731 days. The `reviews` heatmap mode
returns `available: false` with an explanatory message until Phase 3 — review
data is never fabricated as zeros.

Authentication (Phase 5, ADR-0008): all user-data endpoints resolve identity
from the validated server-side session cookie. There is no `X-User-Id`
fallback in any environment; missing/expired/revoked sessions are 401 and
cross-user resources return 404 (no existence leak). State-changing requests
must carry `X-CSRF-Token` (synchronizer token from `GET /auth/csrf`) and a
trusted `Origin`/`Referer` when the client sends one.

Auth endpoints:

| Method | Path | Notes |
| ------ | ---- | ----- |
| POST | `/api/v1/auth/register` | 201 + session cookie + CSRF token; 409 duplicate email; 429 rate-limited (5/h/IP) |
| POST | `/api/v1/auth/login` | 200 + cookie + CSRF; uniform 401 for unknown email / wrong password; 429 with `Retry-After` |
| POST | `/api/v1/auth/logout` | 204; revokes the session server-side (CSRF required) |
| GET  | `/api/v1/auth/me` | current user or 401 |
| GET  | `/api/v1/auth/csrf` | mints the session's CSRF token (rotates) |
| GET  | `/api/v1/auth/sessions` | active sessions metadata |
| POST | `/api/v1/auth/sessions/revoke-all` | revokes every session (CSRF required) |

Password storage: Argon2id (argon2-cffi 25.1.0; m=64MiB t=2 p=4 by default).
Cookies: HttpOnly, SameSite=Lax, host-only; production adds Secure +
`__Host-` prefix. Sessions: absolute 30d / inactivity 7d; only sha256
digests of 256-bit tokens are stored. Email verification and password reset
do not exist yet (no mail provider) and are deliberately not faked.

Codeforces handle policy (ADR-0009): handles are public — any user may
track the same handle; only re-linking by the SAME user conflicts (409).
Quota: `max_linked_accounts` (default 5) per user.

`GET /health` response:

```json
{"status": "ok", "service": "api", "version": "0.1.0", "environment": "local"}
```

## Not yet implemented

Deferred explicitly (not silently missing): email verification, password
reset, per-user settings endpoints, topic/retention analytics endpoints,
a periodic `reconcile` job type, single-problem deep links
(`GET /problems/{problem_id}`), and a professional security audit. The
`reconcile` value exists in the `sync_jobs` job-type model but no scheduler
creates it yet; incremental sync covers the same need today.

## Rules

- All request/response bodies are validated Pydantic models.
- Clients are never authoritative for FSRS state, due dates, or recall
  probabilities — the server computes them.
- List endpoints paginate (`page`, `page_size`) and validate filters.
- Auth-required routes enforce per-user data isolation.
