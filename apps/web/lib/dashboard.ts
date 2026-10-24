"use client";

import type {
  DashboardSummaryResponse,
  HeatmapMode,
  HeatmapResponse,
  ProblemFilters,
  SolvedProblemListResponse,
} from "@codepilot/contracts";
import { apiFetch } from "@/lib/api";

function devHeaders(userId: string): HeadersInit {
  return { "X-User-Id": userId };
}

export function getDashboardSummary(
  userId: string,
  timezone: string,
): Promise<DashboardSummaryResponse> {
  return apiFetch<DashboardSummaryResponse>(
    `/api/v1/dashboard/summary?timezone=${encodeURIComponent(timezone)}`,
    { headers: devHeaders(userId) },
  );
}

export function getHeatmap(
  userId: string,
  params: { from: string; to: string; timezone: string; mode: HeatmapMode },
): Promise<HeatmapResponse> {
  const query = new URLSearchParams({
    from: params.from,
    to: params.to,
    timezone: params.timezone,
    mode: params.mode,
  });
  return apiFetch<HeatmapResponse>(`/api/v1/dashboard/heatmap?${query}`, {
    headers: devHeaders(userId),
  });
}

export function listSolvedProblemsFiltered(
  userId: string,
  filters: ProblemFilters,
): Promise<SolvedProblemListResponse> {
  const query = new URLSearchParams();
  if (filters.search) query.set("search", filters.search);
  if (filters.rating_min !== undefined) query.set("rating_min", String(filters.rating_min));
  if (filters.rating_max !== undefined) query.set("rating_max", String(filters.rating_max));
  if (filters.tag) query.set("tag", filters.tag);
  if (filters.sort) query.set("sort", filters.sort);
  if (filters.order) query.set("order", filters.order);
  query.set("page", String(filters.page ?? 1));
  query.set("page_size", String(filters.page_size ?? 20));
  return apiFetch<SolvedProblemListResponse>(`/api/v1/problems?${query}`, {
    headers: devHeaders(userId),
  });
}
