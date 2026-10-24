"use client";

import type { AuthResponse, AuthUser, CsrfResponse, LoginRequest, RegisterRequest } from "@codepilot/contracts";
import { ApiError, apiFetch, setCsrfToken } from "@/lib/api";

/**
 * Session bootstrap: resolve the authenticated user from the HttpOnly
 * session cookie via GET /auth/me. Returns null when unauthenticated —
 * callers render login states; there is no client-stored identity.
 */
export async function currentUser(): Promise<AuthUser | null> {
  try {
    return await apiFetch<AuthUser>("/api/v1/auth/me");
  } catch {
    return null;
  }
}

/** Fetch (and cache) the CSRF token for the active session. */
export async function refreshCsrfToken(): Promise<string | null> {
  try {
    const body = await apiFetch<CsrfResponse>("/api/v1/auth/csrf");
    setCsrfToken(body.csrf_token);
    return body.csrf_token;
  } catch {
    setCsrfToken(null);
    return null;
  }
}

/** Register + open a session (cookie + CSRF token cached). */
export async function register(payload: RegisterRequest): Promise<AuthUser> {
  const body = await apiFetch<AuthResponse>("/api/v1/auth/register", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  setCsrfToken(body.csrf_token);
  return body.user;
}

/** Login + open a session (cookie + CSRF token cached). */
export async function login(payload: LoginRequest): Promise<AuthUser> {
  const body = await apiFetch<AuthResponse>("/api/v1/auth/login", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  setCsrfToken(body.csrf_token);
  return body.user;
}

/** Revoke the session server-side; the cookie dies with it. */
export async function logout(): Promise<void> {
  try {
    await apiFetch<void>("/api/v1/auth/logout", { method: "POST" });
  } finally {
    setCsrfToken(null);
  }
}

export type SessionState =
  | { phase: "auth"; user: AuthUser }
  | { phase: "anon" } // valid check, no session -> show login CTA
  | { phase: "unreachable" }; // API down: reachability states

/**
 * Standard page bootstrap: current user + a fresh CSRF token for
 * mutations, with an explicit tri-state result.
 */
export async function bootstrapSession(): Promise<SessionState> {
  try {
    const user = await apiFetch<AuthUser>("/api/v1/auth/me");
    await refreshCsrfToken();
    return { phase: "auth", user };
  } catch (exc) {
    if (exc instanceof ApiError && exc.status === 401) return { phase: "anon" };
    return { phase: "unreachable" };
  }
}
