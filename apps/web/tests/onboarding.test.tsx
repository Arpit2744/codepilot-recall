import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import OnboardingPage from "../app/onboarding/page";

/**
 * Minimal fetch surface apiFetch consumes. Routes are "METHOD suffix" keys
 * matched by method + url.endsWith(suffix) — so "/sync-status" can never be
 * captured by the shorter "/codeforces/accounts" route.
 */
let routes: Record<string, (url: string, init?: RequestInit) => unknown> = {};

function routeResponse(url: string, init?: RequestInit) {
  const method = (init?.method ?? "GET").toUpperCase();
  const path = url.split("?")[0]; // strip query: ?page=1&… would break matching
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
      const url = String(input);
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

const DEV_USER = { user_id: "11111111-1111-1111-1111-111111111111", email: "dev-1@example.com", display_name: "Developer" };
const ACCOUNT = {
  id: "22222222-2222-2222-2222-222222222222",
  handle: "tourist",
  verified_at: null,
  last_synced_at: null,
  last_sync_error: null,
  created_at: "2026-10-24T10:00:00Z",
};
const JOB = (status: string, over: Record<string, unknown> = {}) => ({
  id: "33333333-3333-3333-3333-333333333333",
  job_type: "historical",
  status,
  attempt_count: 1,
  started_at: null,
  completed_at: null,
  error_summary: null,
  progress: null,
  created_at: "2026-10-24T10:00:01Z",
  ...over,
});
const STATUS = (jobStatus: string, totals = { submissions: 0, solved_problems: 0 }) => ({
  account: { ...ACCOUNT, last_synced_at: jobStatus === "succeeded" ? "2026-10-24T10:05:00Z" : null },
  latest_jobs: [JOB(jobStatus)],
  totals,
});

afterEach(() => {
  vi.unstubAllGlobals();
  routes = {};
  window.localStorage.clear();
});

test("full flow: dev bootstrap -> connect handle -> poll to success with solved list", async () => {
  stubFetch();
  window.localStorage.removeItem("cpr.dev-user-id");
  routes = {
    "POST /dev/users": () => DEV_USER,
    "GET /sync-status": () => STATUS("pending"),
    "GET /codeforces/accounts": () => [], // no accounts yet: form shows first
    "POST /codeforces/accounts": () => ({ account: ACCOUNT, job: JOB("pending"), queued: false }),
  };

  render(<OnboardingPage />);

  const input = await screen.findByLabelText(/codeforces handle/i);
  await userEvent.type(input, "tourist");
  await userEvent.click(screen.getByRole("button", { name: "Connect" }));

  await waitFor(() => {
    expect(screen.getByText("@tourist")).toBeInTheDocument();
  });
  expect(await screen.findByText("pending")).toBeInTheDocument();

  // Poll flips the job to succeeded and the solved list loads.
  routes = {
    ...routes,
    "GET /sync-status": () => STATUS("succeeded", { submissions: 120, solved_problems: 80 }),
    "GET /problems": () => ({
      items: [
        {
          id: "44444444-4444-4444-4444-444444444444",
          canonical_key: "1-A",
          contest_id: 1,
          problem_index: "A",
          name: "Theatre Square",
          rating: 1000,
          tags: ["math"],
          url: "https://codeforces.com/problemset/problem/1/A",
          first_solved_at: "2024-05-01T12:00:00Z",
          last_solved_at: "2024-05-01T12:00:00Z",
          accepted_count: 1,
        },
      ],
      total: 80,
      page: 1,
      page_size: 10,
    }),
  };

  // The poll interval is 3s; allow two ticks before the flip must land.
  expect(await screen.findByText("succeeded", {}, { timeout: 8000 }), "job chip").toBeInTheDocument();
  expect(await screen.findByText("80 total"), "problem count").toBeInTheDocument();
  expect(screen.getByText(/theatre square/i)).toBeInTheDocument();
  expect(screen.getByText(/solved 2024-05-01/)).toBeInTheDocument();
  expect(screen.getByText("120")).toBeInTheDocument();
});

test("invalid handle shows inline validation without calling the API", async () => {
  stubFetch();
  window.localStorage.setItem("cpr.dev-user-id", DEV_USER.user_id);
  routes = { "GET /codeforces/accounts": () => [] };

  render(<OnboardingPage />);

  const input = await screen.findByLabelText(/codeforces handle/i);
  await userEvent.type(input, "not a handle!");
  await userEvent.click(screen.getByRole("button", { name: "Connect" }));

  expect(
    await screen.findByText(/1-24 letters, digits, dot, underscore or hyphen/i),
  ).toBeInTheDocument();
  expect(vi.mocked(fetch)).not.toHaveBeenCalledWith(
    expect.stringContaining("POST"),
    expect.anything(),
  );
});

test("API-down bootstrap shows the reachability banner with retry", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      throw new TypeError("fetch failed");
    }),
  );

  render(<OnboardingPage />);

  expect(
    await screen.findByText(/could not reach the api to start a local session/i),
  ).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
});

test("failed sync surfaces the error summary", async () => {
  stubFetch();
  window.localStorage.setItem("cpr.dev-user-id", DEV_USER.user_id);
  routes = {
    "GET /codeforces/accounts": () => [ACCOUNT],
    "GET /sync-status": () => ({
      account: ACCOUNT,
      latest_jobs: [JOB("failed", { error_summary: "handle not found: tourist" })],
      totals: { submissions: 0, solved_problems: 0 },
    }),
  };

  render(<OnboardingPage />);

  expect(await screen.findByText("failed", {}, { timeout: 4000 })).toBeInTheDocument();
  // The summary intentionally appears in the hint line AND the alert box.
  const alerts = await screen.findAllByRole("alert", {}, { timeout: 4000 });
  expect(alerts[0].textContent).toMatch(/handle not found: tourist/i);
  expect(screen.getByRole("button", { name: "Sync now" })).toBeInTheDocument();
});
