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

/**
 * In-memory CSRF token for the current session. The session itself lives in
 * an HttpOnly cookie the browser manages; JS only ever holds the CSRF token
 * (never a bearer/session secret).
 */
let csrfToken: string | null = null;

export function setCsrfToken(token: string | null): void {
  csrfToken = token;
}

export function currentCsrfToken(): string | null {
  return csrfToken;
}

function isRetryableCsrfFailure(status: number, code: string): boolean {
  return status === 403 && code === "http_403";
}

async function rawFetch(path: string, init?: RequestInit): Promise<Response> {
  const method = (init?.method ?? "GET").toUpperCase();
  const headers: Record<string, string> = {
    ...(init?.headers as Record<string, string> | undefined),
  };
  if (init?.body && !headers["content-type"]) {
    headers["content-type"] = "application/json"; // browsers default text/plain
  }
  if (method !== "GET" && method !== "HEAD" && csrfToken) {
    headers["X-CSRF-Token"] = csrfToken;
  }
  return fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: "include", // session cookie
    headers,
  });
}

async function ensureCsrfToken(): Promise<void> {
  if (csrfToken !== null) return;
  try {
    const resp = await fetch(`${API_BASE_URL}/api/v1/auth/csrf`, { credentials: "include" });
    if (resp.ok) {
      csrfToken = ((await resp.json()) as { csrf_token: string }).csrf_token;
    }
  } catch {
    /* unauthenticated or unreachable: the request proceeds and fails honestly */
  }
}

/** Typed JSON fetch with cookies + automatic CSRF handling. */
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method ?? "GET").toUpperCase();
  if (method !== "GET" && method !== "HEAD") {
    await ensureCsrfToken(); // buttons can fire before page bootstrap caches it
  }
  let response = await rawFetch(path, init);
  let error = await toApiError(response);

  if (error && isRetryableCsrfFailure(error.status, error.code) && csrfToken !== null) {
    // The token may have been rotated (another tab fetched /auth/csrf):
    // refresh once and retry the mutation.
    try {
      const refresh = await rawFetch("/api/v1/auth/csrf");
      if (refresh.ok) {
        csrfToken = ((await refresh.json()) as { csrf_token: string }).csrf_token;
        response = await rawFetch(path, init);
        error = await toApiError(response);
      }
    } catch {
      /* fall through with the original error */
    }
  }

  if (error) throw error;
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

async function toApiError(response: Response): Promise<ApiError | null> {
  if (response.ok) return null;
  let code = `http_${response.status}`;
  let message = response.statusText || "Request failed";
  try {
    const body = (await response.json()) as ApiErrorResponse;
    if (body?.error?.code) code = body.error.code;
    if (body?.error?.message) message = body.error.message;
  } catch {
    // Non-JSON error body; keep the HTTP-derived defaults.
  }
  return new ApiError(response.status, code, message);
}
