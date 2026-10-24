import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import DashboardPage from "../app/dashboard/page";

/** Same routing harness as the onboarding tests: "METHOD suffix" keys. */
let routes: Record<string, (url: string, init?: RequestInit) => unknown> = {};

function routeResponse(url: string, init?: RequestInit) {
  const method = (init?.method ?? "GET").toUpperCase();
  const path = url.split("?")[0];
  for (const pattern of Object.keys(routes)) {
    const [routeMethod, suffix] = pattern.split(" ");
    if (routeMethod === method && path.endsWith(suffix)) {
      return routes[pattern](url, init);
    }
  }
  throw new Error(`unexpected fetch ${method} ${url}`);
}

function stubFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const result = routeResponse(String(input), init);
      if (result instanceof Error) throw result;
      return { ok: true, status: 200, statusText: "OK", json: async () => result } as unknown as Response;
    }),
  );
}

const DEV_USER = { user_id: "11111111-1111-1111-1111-111111111111" };
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
    recent_first_solves: [
      {
        problem_id: "33333333-3333-3333-3333-333333333333",
        name: "Theatre Square",
        contest_id: 1,
        problem_index: "A",
        rating: 1000,
        first_solved_at: "2026-10-20T10:00:00Z",
      },
    ],
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

const FULL_ROUTES = {
  "GET /codeforces/accounts": () => [ACCOUNT],
  "GET /dashboard/summary": () => summary(),
  "GET /dashboard/heatmap": (url: string) =>
    url.includes("mode=reviews")
      ? heatmap("reviews", { available: false, days: [], max_count: 0, message: "Review sessions are tracked from Phase 3." })
      : heatmap(url.includes("mode=first_solves") ? "first_solves" : "submissions"),
  "GET /problems": () => problems(),
};

afterEach(() => {
  vi.unstubAllGlobals();
  routes = {};
  window.localStorage.clear();
});

test("renders summary cards from the real API", async () => {
  stubFetch();
  window.localStorage.setItem("cpr.dev-user-id", DEV_USER.user_id);
  routes = FULL_ROUTES;

  render(<DashboardPage />);

  expect(await screen.findByText("421")).toBeInTheDocument();
  expect(screen.getByText("187")).toBeInTheDocument();
  expect(screen.getByText("6d")).toBeInTheDocument();
  expect(screen.getByText(/dates are local calendar days in utc/i)).toBeInTheDocument();
});

test("heatmap mode switching including real reviews mode", async () => {
  stubFetch();
  window.localStorage.setItem("cpr.dev-user-id", DEV_USER.user_id);
  routes = FULL_ROUTES;

  render(<DashboardPage />);
  await screen.findByText("421");

  // Phase 3: Reviews is a real mode (completed sessions from the backend).
  await userEvent.click(screen.getByRole("tab", { name: "Reviews" }));
  expect(screen.getByRole("tab", { name: "Reviews" })).toHaveAttribute(
    "aria-selected",
    "true",
  );

  // First solves is selectable too.
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
  window.localStorage.setItem("cpr.dev-user-id", DEV_USER.user_id);
  routes = { "GET /codeforces/accounts": () => [] };

  render(<DashboardPage />);

  const cta = await screen.findByRole("link", { name: /connect your handle/i });
  expect(cta).toHaveAttribute("href", "/onboarding");
  expect(screen.queryByText("421")).not.toBeInTheDocument();
});

test("problems table renders rows and paginates", async () => {
  stubFetch();
  window.localStorage.setItem("cpr.dev-user-id", DEV_USER.user_id);
  let requestedUrl = "";
  routes = {
    ...FULL_ROUTES,
    "GET /problems": (url) => {
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
    },
  };

  render(<DashboardPage />);
  expect(await screen.findByText("Theatre Square")).toBeInTheDocument();
  expect(screen.getByText("25 total")).toBeInTheDocument();
  expect(screen.getByText(/page 1 of 3/i)).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Next" }));
  await waitFor(() => {
    expect(requestedUrl).toContain("page=2");
  });
});

test("filters pass through to the API after debounce", async () => {
  stubFetch();
  window.localStorage.setItem("cpr.dev-user-id", DEV_USER.user_id);
  vi.useFakeTimers({ shouldAdvanceTime: true });
  try {
    let requestedUrl = "";
    routes = {
      ...FULL_ROUTES,
      "GET /problems": (url) => {
        requestedUrl = url;
        return problems();
      },
    };

    render(<DashboardPage />);
    await screen.findByText(/solved problems/i);

    await userEvent.type(screen.getByLabelText(/search name/i), "square");
    await vi.advanceTimersByTimeAsync(400);

    await waitFor(() => {
      expect(requestedUrl).toContain("search=square");
    });
  } finally {
    vi.useRealTimers();
  }
});

test("empty problems state distinguishes filters from no data", async () => {
  stubFetch();
  window.localStorage.setItem("cpr.dev-user-id", DEV_USER.user_id);
  routes = {
    ...FULL_ROUTES,
    "GET /problems": () => problems([], 0),
  };

  render(<DashboardPage />);
  expect(
    await screen.findByText(/no solved problems match these filters/i),
  ).toBeInTheDocument();
});

test("API failure shows honest unavailable states, never fake numbers", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      throw new TypeError("network down");
    }),
  );
  window.localStorage.setItem("cpr.dev-user-id", DEV_USER.user_id);

  render(<DashboardPage />);

  expect(await screen.findByText(/summary unavailable/i)).toBeInTheDocument();
  expect(await screen.findByText(/activity unavailable right now/i)).toBeInTheDocument();
  expect(await screen.findByText(/could not load solved problems/i)).toBeInTheDocument();
  expect(screen.queryByText("421")).not.toBeInTheDocument();
});
