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
