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

// Phase 5: identity comes from the HttpOnly session cookie
// (credentials: include in apiFetch); no client-supplied user ids.

export function createDevUser(): Promise<DevUserResponse> {
  return apiFetch<DevUserResponse>("/api/v1/dev/users", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export function createAccount(payload: CreateAccountRequest): Promise<AccountCreatedResponse> {
  return apiFetch<AccountCreatedResponse>("/api/v1/codeforces/accounts", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listAccounts(): Promise<CfAccount[]> {
  return apiFetch<CfAccount[]>("/api/v1/codeforces/accounts");
}

export function getSyncStatus(accountId: string): Promise<SyncStatusResponse> {
  return apiFetch<SyncStatusResponse>(
    `/api/v1/codeforces/accounts/${accountId}/sync-status`,
  );
}

export function triggerSync(accountId: string): Promise<SyncTriggerResponse> {
  return apiFetch<SyncTriggerResponse>(`/api/v1/codeforces/accounts/${accountId}/sync`, {
    method: "POST",
  });
}

export function listSolvedProblems(
  page = 1,
  pageSize = 10,
): Promise<SolvedProblemListResponse> {
  return apiFetch<SolvedProblemListResponse>(
    `/api/v1/problems?page=${page}&page_size=${pageSize}`,
  );
}
