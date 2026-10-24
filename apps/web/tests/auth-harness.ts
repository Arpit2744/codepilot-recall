/**
 * Shared fetch stub for authenticated-page tests (Phase 5).
 *
 * Session identity comes from the cookie the API would set; tests stub
 * GET /auth/me + GET /auth/csrf so `bootstrapSession()` succeeds, and page
 * mutations carry the stubbed CSRF token automatically via apiFetch.
 */
import { vi } from "vitest";
import { setCsrfToken } from "../lib/api";

type Route = (url: string, init?: RequestInit) => unknown;

let routes: Record<string, Route> = {};

export const DEV_USER = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "dev@example.com",
  display_name: "Developer",
  created_at: "2026-10-01T00:00:00Z",
};

export function stubAuthSession(user: unknown = DEV_USER) {
  routes["GET /auth/me"] = () => user;
  routes["GET /auth/csrf"] = () => ({ csrf_token: "test-csrf-token" });
  setCsrfToken("test-csrf-token");
}

export function stubAnonSession() {
  setCsrfToken(null);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/auth/me") || url.includes("/auth/csrf")) {
        return {
          ok: false,
          status: 401,
          statusText: "Unauthorized",
          json: async () => ({
            error: { code: "http_401", message: "Authentication required", details: null },
          }),
        } as unknown as Response;
      }
      const result = routeResponse(url, init);
      if (result instanceof Error) throw result;
      return {
        ok: true,
        status: 200,
        statusText: "OK",
        json: async () => result,
      } as unknown as Response;
    }),
  );
}

export function setRoute(pattern: string, handler: Route) {
  routes[pattern] = handler;
}

export function clearRoutes() {
  routes = {};
}

function routeResponse(url: string, init?: RequestInit) {
  const method = (init?.method ?? "GET").toUpperCase();
  const path = url.split("?")[0];
  const patterns = Object.keys(routes).sort((a, b) => b.length - a.length);
  for (const pattern of patterns) {
    const [routeMethod, suffix] = pattern.split(" ");
    if (routeMethod === method && path.endsWith(suffix)) {
      return routes[pattern](url, init);
    }
  }
  throw new Error(`unexpected fetch ${method} ${url}`);
}

export function stubFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const result = routeResponse(String(input), init);
      if (result instanceof Error) throw result;
      return {
        ok: true,
        status: 200,
        statusText: "OK",
        json: async () => result,
      } as unknown as Response;
    }),
  );
}

/** Fetch stub that 401s /auth/me (session gone) but serves other routes. */
export function stubExpiredSession() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/auth/me")) {
        return {
          ok: false,
          status: 401,
          statusText: "Unauthorized",
          json: async () => ({
            error: { code: "http_401", message: "Authentication required", details: null },
          }),
        } as unknown as Response;
      }
      const result = routeResponse(url, init);
      return {
        ok: true,
        status: 200,
        statusText: "OK",
        json: async () => result,
      } as unknown as Response;
    }),
  );
}

/** Everything fails — API unreachable. */
export function stubApiDown() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      throw new TypeError("network down");
    }),
  );
}
