"use client";

import type {
  AccountCreatedResponse,
  CfAccount,
  CreateAccountRequest,
  DevUserResponse,
  SolvedProblemListResponse,
  SyncStatusResponse,
  SyncTriggerResponse,
} from "@codepilot/contracts";
import { apiFetch } from "@/lib/api";

/**
 * Phase 1 development auth boundary: every request carries the dev user id.
 * Phase 5 replaces this header with real session authentication.
 */
function devHeaders(userId: string): HeadersInit {
  return { "X-User-Id": userId };
}

export function createDevUser(): Promise<DevUserResponse> {
  return apiFetch<DevUserResponse>("/api/v1/dev/users", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function createAccount(
  userId: string,
  payload: CreateAccountRequest,
): Promise<AccountCreatedResponse> {
  return apiFetch<AccountCreatedResponse>("/api/v1/codeforces/accounts", {
    method: "POST",
    headers: devHeaders(userId),
    body: JSON.stringify(payload),
  });
}

export function listAccounts(userId: string): Promise<CfAccount[]> {
  return apiFetch<CfAccount[]>("/api/v1/codeforces/accounts", {
    headers: devHeaders(userId),
  });
}

export function getSyncStatus(userId: string, accountId: string): Promise<SyncStatusResponse> {
  return apiFetch<SyncStatusResponse>(
    `/api/v1/codeforces/accounts/${accountId}/sync-status`,
    { headers: devHeaders(userId) },
  );
}

export function triggerSync(userId: string, accountId: string): Promise<SyncTriggerResponse> {
  return apiFetch<SyncTriggerResponse>(`/api/v1/codeforces/accounts/${accountId}/sync`, {
    method: "POST",
    headers: devHeaders(userId),
  });
}

export function listSolvedProblems(
  userId: string,
  page = 1,
  pageSize = 10,
): Promise<SolvedProblemListResponse> {
  return apiFetch<SolvedProblemListResponse>(
    `/api/v1/problems?page=${page}&page_size=${pageSize}`,
    { headers: devHeaders(userId) },
  );
}
