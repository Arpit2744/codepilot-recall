import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import DashboardPage from "../app/dashboard/page";
import { clearRoutes, setRoute, stubAnonSession, stubApiDown, stubAuthSession, stubFetch } from "./auth-harness";

const ACCOUNT = {
  id: "22222222-2222-2222-2222-222222222222",
  handle: "tourist",
  verified_at: null,
  last_synced_at: "2026-10-24T10:00:00Z",
  last_sync_error: null,
  created_at: "2026-10-24T09:00:00Z",
};

function summary(over: Record<string, unknown> = {}) {
  return {
    timezone: "UTC",
    generated_at: "2026-10-24T12:00:00Z",
    totals: { submissions: 421, solved_problems: 187 },
    current_streak_days: 6,
    recent_first_solves: [],
    accounts: [ACCOUNT],
    ...over,
  };
}

function heatmap(mode: string, over: Record<string, unknown> = {}) {
  return {
    timezone: "UTC",
    mode,
    from: "2026-04-25",
    to: "2026-10-24",
    available: true,
    days: [
      { date: "2026-04-25", count: 0 },
      { date: "2026-04-26", count: 3 },
      { date: "2026-04-27", count: 7 },
    ],
    max_count: 7,
    message: null,
    ...over,
  };
}

function problems(items: unknown[] = [], total = items.length, page = 1) {
  return { items, total, page, page_size: 10 };
}

function fullRoutes() {
  setRoute("GET /codeforces/accounts", () => [ACCOUNT]);
  setRoute("GET /dashboard/summary", () => summary());
  setRoute("GET /dashboard/heatmap", (url: string) =>
    url.includes("mode=reviews")
      ? heatmap("reviews")
      : heatmap(url.includes("mode=first_solves") ? "first_solves" : "submissions"),
  );
  setRoute("GET /problems", () => problems());
}

afterEach(() => {
  vi.unstubAllGlobals();
  clearRoutes();
});

test("renders summary cards from the real API", async () => {
  stubFetch();
  stubAuthSession();
  fullRoutes();

  render(<DashboardPage />);

  expect(await screen.findByText("421")).toBeInTheDocument();
  expect(screen.getByText("187")).toBeInTheDocument();
  expect(screen.getByText("6d")).toBeInTheDocument();
});

test("heatmap mode switching including real reviews mode", async () => {
  stubFetch();
  stubAuthSession();
  fullRoutes();

  render(<DashboardPage />);
  await screen.findByText("421");

  await userEvent.click(screen.getByRole("tab", { name: "Reviews" }));
  expect(screen.getByRole("tab", { name: "Reviews" })).toHaveAttribute("aria-selected", "true");

  await userEvent.click(screen.getByRole("tab", { name: "First solves" }));
  await waitFor(() => {
    expect(screen.getByRole("tab", { name: "First solves" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });
});

test("no account connected shows the onboarding call to action", async () => {
  stubFetch();
  stubAuthSession();
  setRoute("GET /codeforces/accounts", () => []);

  render(<DashboardPage />);

  const cta = await screen.findByRole("link", { name: /connect your handle/i });
  expect(cta).toHaveAttribute("href", "/onboarding");
  expect(screen.queryByText("421")).not.toBeInTheDocument();
});

test("unauthenticated users see the login CTA", async () => {
  stubAnonSession();

  render(<DashboardPage />);
  const cta = await screen.findByRole("link", { name: /^log in$/i });
  expect(cta).toHaveAttribute("href", "/login");
  expect(screen.queryByText("421")).not.toBeInTheDocument();
});

test("problems table renders rows and paginates", async () => {
  stubFetch();
  stubAuthSession();
  fullRoutes();
  let requestedUrl = "";
  setRoute("GET /problems", (url) => {
    requestedUrl = url;
    return problems(
      [
        {
          id: "44444444-4444-4444-4444-444444444444",
          canonical_key: "1-A",
          contest_id: 1,
          problem_index: "A",
          name: "Theatre Square",
          rating: 1000,
          tags: ["math"],
          url: null,
          first_solved_at: "2026-10-20T10:00:00Z",
          last_solved_at: "2026-10-20T10:00:00Z",
          accepted_count: 2,
        },
      ],
      25,
    );
  });

  render(<DashboardPage />);
  expect(await screen.findByText("Theatre Square")).toBeInTheDocument();
  expect(screen.getByText("25 total")).toBeInTheDocument();
  expect(screen.getByText(/page 1 of 3/i)).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Next" }));
  await waitFor(() => {
    expect(requestedUrl).toContain("page=2");
  });
});

test("empty problems state distinguishes filters from no data", async () => {
  stubFetch();
  stubAuthSession();
  fullRoutes();
  setRoute("GET /problems", () => problems([], 0));

  render(<DashboardPage />);
  expect(await screen.findByText(/no solved problems match these filters/i)).toBeInTheDocument();
});

test("API failure shows honest unavailable states, never fake numbers", async () => {
  stubApiDown();

  render(<DashboardPage />);

  expect(await screen.findByText(/could not reach the api/i)).toBeInTheDocument();
  expect(screen.queryByText("421")).not.toBeInTheDocument();
});
