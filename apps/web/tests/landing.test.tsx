import { render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import Home from "../app/page";
import { clearRoutes, setRoute, stubApiDown, stubAuthSession, stubFetch } from "./auth-harness";

afterEach(() => {
  vi.unstubAllGlobals();
  clearRoutes();
});

test("renders the hero heading and feature cards (authenticated visitor)", async () => {
  stubFetch();
  stubAuthSession();
  setRoute("GET /codeforces/accounts", () => []);

  render(<Home />);

  expect(
    screen.getByRole("heading", { level: 1, name: /remember every problem/i }),
  ).toBeInTheDocument();
  expect(screen.getByText("True first-solve dates")).toBeInTheDocument();
  expect(screen.getByText("Activity heatmap")).toBeInTheDocument();
  expect(screen.getByText("Adaptive revision")).toBeInTheDocument();
  // Authenticated without a handle: connect CTA, no Log in.
  expect(await screen.findByRole("link", { name: /connect your handle/i })).toHaveAttribute(
    "href",
    "/onboarding",
  );
  expect(screen.queryByRole("link", { name: /^log in$/i })).not.toBeInTheDocument();
});

test("renders feature content even when the API is unreachable", async () => {
  stubApiDown();

  render(<Home />);

  expect(
    screen.getByRole("heading", { level: 1, name: /remember every problem/i }),
  ).toBeInTheDocument();
  // Unreachable is distinct from anonymous: no Log in CTA is injected.
  expect(await screen.findByText(/session status unavailable/i)).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /^log in$/i })).not.toBeInTheDocument();
});
