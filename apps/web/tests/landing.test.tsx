import { render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import Home from "../app/page";

function stubHealthResponse(body: unknown, ok = true) {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        ({
          ok,
          status: ok ? 200 : 503,
          statusText: ok ? "OK" : "Service Unavailable",
          json: async () => body,
        }) as unknown as Response,
    ),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

test("renders the hero heading and feature cards", () => {
  stubHealthResponse({
    status: "ok",
    service: "api",
    version: "0.1.0",
    environment: "test",
  });
  render(<Home />);

  expect(
    screen.getByRole("heading", { level: 1, name: /remember every problem/i }),
  ).toBeInTheDocument();
  expect(screen.getByText("True first-solve dates")).toBeInTheDocument();
  expect(screen.getByText("Activity heatmap")).toBeInTheDocument();
  expect(screen.getByText("Adaptive revision")).toBeInTheDocument();
});

test("renders feature content even when the API is unreachable", () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      throw new TypeError("fetch failed");
    }),
  );
  render(<Home />);

  expect(
    screen.getByRole("heading", { level: 1, name: /remember every problem/i }),
  ).toBeInTheDocument();
});
