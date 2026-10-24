# ADR-0003: Store UTC, bucket calendar days in the user's timezone

Date: 2026-10-24 · Status: accepted

## Context

Activity heatmaps and "due today" queues depend on calendar days, which
depend on the user's timezone. Codeforces supplies Unix timestamps (UTC).

## Decision

- Every event timestamp (`submitted_at`, `first_solved_at`, review times,
  due dates) is stored as timezone-aware UTC (`TIMESTAMPTZ` /
  `DateTime(timezone=True)`).
- Heatmap days and daily rollup keys are computed by converting UTC instants
  into `users.timezone` (IANA name, default `UTC`) before truncation.
- Source creation timestamps — never submission IDs — derive original solve
  dates.

## Consequences

- A solve at 23:30 UTC lands on the next calendar day for a UTC+2 user and
  on the previous day for a UTC−5 user — matching each user's lived
  experience.
- Timezone-boundary tests are first-class from Phase 2 (Phase exit
  criterion).
- Users can change timezone; historical day bucketing recomputes from
  stored UTC instants, never from pre-bucketed values.
