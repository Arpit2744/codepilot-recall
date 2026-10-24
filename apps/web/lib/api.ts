import type { ApiErrorResponse } from "@codepilot/contracts";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Typed JSON fetch against the CodePilot Recall API. */
export async function apiFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "content-type": "application/json",
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    let code = `http_${response.status}`;
    let message = response.statusText || "Request failed";
    try {
      const body = (await response.json()) as ApiErrorResponse;
      if (body?.error?.code) code = body.error.code;
      if (body?.error?.message) message = body.error.message;
    } catch {
      // Non-JSON error body; keep the HTTP-derived defaults.
    }
    throw new ApiError(response.status, code, message);
  }

  return (await response.json()) as T;
}
