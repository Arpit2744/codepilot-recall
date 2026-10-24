import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ApiStatus } from "../components/api-status";

/** Stub fetch with the minimal surface apiFetch consumes. */
function stubFetch(body: unknown, ok: boolean, status: number) {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        ({
          ok,
          status,
          statusText: ok ? "OK" : "Service Unavailable",
          json: async () => body,
        }) as unknown as Response,
    ),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

test("shows API online with version when /health succeeds", async () => {
  stubFetch(
    { status: "ok", service: "api", version: "0.1.0", environment: "test" },
    true,
    200,
  );

  render(<ApiStatus />);

  await waitFor(() => {
    expect(screen.getByText("API online")).toBeInTheDocument();
  });
  expect(screen.getByText("v0.1.0")).toBeInTheDocument();
});

test("shows API unreachable when /health returns an HTTP error", async () => {
  // Non-JSON error body: apiFetch must still produce a clean ApiError.
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        ({
          ok: false,
          status: 503,
          statusText: "Service Unavailable",
          json: async () => {
            throw new SyntaxError("not JSON");
          },
        }) as unknown as Response,
    ),
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
