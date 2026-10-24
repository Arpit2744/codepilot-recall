/**
 * Shared API contract types for CodePilot Recall.
 *
 * Type-only by design: the package ships no runtime code, so it can be
 * consumed from source by both Next.js (transpilePackages) and Vitest
 * without a build step. Keep every export a `type`/`interface`.
 *
 * These mirror services/api/app/schemas — update both sides together.
 */

export interface HealthResponse {
  status: "ok";
  service: string;
  version: string;
  environment: string;
}

export interface ReadinessResponse extends HealthResponse {
  database: "ok";
}

export interface ApiRootResponse {
  name: string;
  version: string;
  status: string;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  details: unknown;
}

export interface ApiErrorResponse {
  error: ApiErrorBody;
}

/** Pagination envelope used by all list endpoints (Phase 2+). */
export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

// ---------------------------------------------------------------------------
// Codeforces integration (Phase 1)

export interface CfAccount {
  id: string;
  handle: string;
  verified_at: string | null;
  last_synced_at: string | null;
  last_sync_error: string | null;
  created_at: string;
}

export type SyncJobType = "historical" | "incremental" | "reconcile";
export type SyncJobStatus = "pending" | "running" | "succeeded" | "failed" | "cancelled";

export interface SyncJob {
  id: string;
  job_type: SyncJobType;
  status: SyncJobStatus;
  attempt_count: number;
  started_at: string | null;
  completed_at: string | null;
  error_summary: string | null;
  progress: { pages_fetched?: number; submissions_seen?: number; new_submissions?: number } | null;
  created_at: string;
}

export interface AccountCreatedResponse {
  account: CfAccount;
  job: SyncJob;
  queued: boolean;
}

export interface SyncTriggerResponse {
  account: CfAccount;
  job: SyncJob;
  queued: boolean;
  already_active: boolean;
}

export interface SyncTotals {
  submissions: number;
  solved_problems: number;
}

export interface SyncStatusResponse {
  account: CfAccount;
  latest_jobs: SyncJob[];
  totals: SyncTotals;
}

export interface SolvedProblem {
  id: string;
  canonical_key: string;
  contest_id: number | null;
  problem_index: string | null;
  name: string;
  rating: number | null;
  tags: string[];
  url: string | null;
  first_solved_at: string;
  last_solved_at: string;
  accepted_count: number;
}

export type SolvedProblemListResponse = Paginated<SolvedProblem>;

export interface CreateAccountRequest {
  handle: string;
}

export interface DevUserResponse {
  user_id: string;
  email: string;
  display_name: string;
}
