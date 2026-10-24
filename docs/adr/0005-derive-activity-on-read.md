# ADR-0005: Derive daily activity on read instead of materializing daily_activity

Date: 2026-10-24 · Status: accepted

## Context

The Phase 2 checklist considered a `daily_activity` rollup table. Dashboard
aggregates must be timezone-correct (bucket by the requested IANA zone's
local midnight), immune to duplicate syncs, and consistent with source
records even when re-syncs discover older first solves.

## Decision

Compute activity aggregates **on read** from the canonical tables
(`submissions`, `user_problems`), converting each UTC timestamp into the
requested timezone before assigning a local date. No materialized table.

Migration `0003` adds the indexes the queries need:
`submissions(cf_account_id, submitted_at)` and
`user_problems(user_id, first_solved_at)`.

## Why not a rollup table

1. **Timezone dependence.** A date-keyed rollup is only valid for one
   timezone; users may change theirs (ADR-0003), which would invalidate
   every stored row. Query-time bucketing adapts for free.
2. **Invalidation complexity vs. data size.** Correct invalidation needs to
   handle re-syncs discovering older solves (min-semantics moves a first
   solve backwards across days), verdict refreshes, and historical imports.
   Per-user data (hundreds to low tens of thousands of rows in realistic
   ranges) aggregates in milliseconds — the cache would only add risk.
3. **Consistency by construction.** `submissions` is unique on
   `(cf_account_id, cf_submission_id)` and `user_problems` on
   `(user_id, problem_id)`; derived counts can never diverge from source
   records, so repeated syncs cannot inflate them and there is nothing to
   reconcile.

## Consequences

- Aggregate endpoints scan indexed ranges; a materialized rollup can be
  introduced later behind the same repository functions if data volumes
  ever demand it.
- Heatmap ranges are capped (`MAX_HEATMAP_DAYS = 731`) to bound work.
- The streak computation reuses the same derived date sets (lookback
  window of 400 days).
