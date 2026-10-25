import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ApiStatus } from "../components/api-status";

let requestedUrls: string[] = [];

/**
 * Stub fetch with the minimal surface apiFetch consumes, recording every
 * requested URL so tests can pin the same-origin health path.
 */
function stubFetch(body: unknown, ok: boolean, status: number) {
  requestedUrls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      requestedUrls.push(String(input));
      expect(init?.credentials ?? undefined).not.toBe("omit");
      return {
        ok,
        status,
        statusText: ok ? "OK" : "Service Unavailable",
        json: async () => body,
      } as unknown as Response;
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

test("polls the same-origin /api/v1/health proxy path, not the backend path", async () => {
  stubFetch(
    { status: "ok", service: "api", version: "0.1.0", environment: "production" },
    true,
    200,
  );

  render(<ApiStatus />);

  await waitFor(() => {
    expect(screen.getByText("API online")).toBeInTheDocument();
  });
  expect(screen.getByText("v0.1.0")).toBeInTheDocument();
  expect(requestedUrls).toEqual(["/api/v1/health"]);
});

test("shows API unreachable when the proxy returns an HTTP error", async () => {
  // Non-JSON error body: apiFetch must still produce a clean ApiError.
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: false,
      status: 502,
      statusText: "Bad Gateway",
      json: async () => {
        throw new SyntaxError("not JSON");
      },
    }) as unknown as Response),
  );

  render(<ApiStatus />);

  await waitFor(() => {
    expect(screen.getByText("API unreachable")).toBeInTheDocument();
  });
});

test("shows API unreachable when fetch throws", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      throw new TypeError("network down");
    }),
  );

  render(<ApiStatus />);

  await waitFor(() => {
    expect(screen.getByText("API unreachable")).toBeInTheDocument();
  });
});
