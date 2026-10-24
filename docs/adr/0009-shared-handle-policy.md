# ADR-0009: Codeforces handles are shared, not claimed

Date: 2026-10-25 · Status: accepted

## Context

Phase 1 enforced one global owner per handle (`UNIQUE(handle_lower)`) with
no ownership verification. Phase 5 must choose: keep exclusivity (requiring
a real ownership-verification mechanism) or allow sharing.

A public Codeforces username proves nothing about control of the account.
Codeforces offers no OAuth/delegation API, and spoofable flows (e.g.
"submit a marker submission") are unverifiable without scraping private
data — so an *exclusive* claim cannot be defended.

## Decision

Any registered user may track any public handle. Migration `0005` replaces
the global unique constraint with `UNIQUE(user_id, handle_lower)` (same
user re-linking the same handle still 409s). Syncing the same handle from
two accounts creates independent `cf_accounts`, `sync_jobs`, and
`submissions` rows; `user_problems` rollups and FSRS memory stay scoped to
each user by the existing keys. Codeforces passwords are never requested.

## Consequences

- Duplicate upstream fetches for a popular handle respect the shared rate
  limiter; acceptable at beta scale.
- If Codeforces ever offers real handle verification, an ownership model
  can be layered on without schema breakage (add a verified flag).
