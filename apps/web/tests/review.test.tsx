import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import ReviewPage from "../app/review/page";

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
const PROBLEM = {
  id: "55555555-5555-5555-5555-555555555555",
  name: "Theatre Square",
  contest_id: 1,
  problem_index: "A",
  rating: 1000,
  tags: ["math"],
  url: "https://codeforces.com/problemset/problem/1/A",
};
const SESSION = {
  id: "66666666-6666-6666-6666-666666666666",
  problem_id: PROBLEM.id,
  status: "pending",
  started_at: "2026-10-24T12:00:00Z",
  completed_at: null,
  outcome: null,
  independent: null,
  help_level: null,
  duration_seconds: null,
  notes: null,
};
const MEMORY = {
  due_at: "2026-11-05T12:00:00Z",
  last_review_at: "2026-10-24T12:00:00Z",
  stability: 11.68,
  difficulty: 5.1,
  repetitions: 1,
  lapses: 0,
  scheduler_version: "fsrs-6.3.2",
};

afterEach(() => {
  vi.unstubAllGlobals();
  routes = {};
  window.localStorage.clear();
});

test("empty queue explains honestly; no fabricated reviews", async () => {
  stubFetch();
  window.localStorage.setItem("cpr.dev-user-id", DEV_USER.user_id);
  routes = { "GET /reviews/due": () => ({ items: [] }) };

  render(<ReviewPage />);
  expect(await screen.findByText(/nothing due right now/i)).toBeInTheDocument();
  expect(
    screen.getByText(/a codeforces acceptance alone never creates a review/i),
  ).toBeInTheDocument();
});

test("due queue lists problems and starts a session with outcome controls", async () => {
  stubFetch();
  window.localStorage.setItem("cpr.dev-user-id", DEV_USER.user_id);
  routes = {
    "GET /reviews/due": () => ({
      items: [
        {
          problem: PROBLEM,
          due_at: "2026-10-20T08:00:00Z",
          last_review_at: "2026-10-10T08:00:00Z",
          repetitions: 3,
          lapses: 1,
        },
      ],
    }),
    "POST /reviews/sessions": () => ({ session: SESSION, problem: PROBLEM, memory: null }),
  };

  render(<ReviewPage />);
  expect(await screen.findByText(/Theatre Square/)).toBeInTheDocument();
  expect(screen.getByText(/3 reviews · 1 lapse/)).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: /start review/i }));

  expect(await screen.findByRole("heading", { name: /theatre square/i })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /open problem on codeforces/i })).toHaveAttribute(
    "href",
    PROBLEM.url,
  );
  for (const label of ["Again", "Hard", "Good", "Easy"]) {
    expect(screen.getByRole("button", { name: new RegExp(`^${label}`) })).toBeInTheDocument();
  }
});

test("submitting an outcome shows the next due date from the backend", async () => {
  stubFetch();
  window.localStorage.setItem("cpr.dev-user-id", DEV_USER.user_id);
  routes = {
    "GET /reviews/due": () => ({ items: [] }),
    "POST /reviews/sessions": () => ({ session: SESSION, problem: PROBLEM, memory: null }),
    "POST /complete": () => ({
      session: { ...SESSION, status: "completed", outcome: "good", independent: true, help_level: "none" },
      problem: PROBLEM,
      memory: MEMORY,
    }),
  };

  // Deep link starts the session automatically on mount.
  window.history.pushState({}, "", "/review?problem=" + PROBLEM.id);
  render(<ReviewPage />);
  expect(await screen.findByRole("button", { name: /^Good/ })).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: /^Good/ }));

  expect(await screen.findByText(/review recorded/i)).toBeInTheDocument();
  expect(screen.getByText(/2026-11-05 12:00 UTC/i)).toBeInTheDocument();
  expect(screen.getByText(/fsrs-6\.3\.2/i)).toBeInTheDocument();
  window.history.pushState({}, "", "/review");
});

test("409 conflict shows already-completed state without a second advance", async () => {
  stubFetch();
  window.localStorage.setItem("cpr.dev-user-id", DEV_USER.user_id);
  routes = {
    "GET /reviews/due": () => ({ items: [] }),
    "POST /reviews/sessions": () => ({ session: SESSION, problem: PROBLEM, memory: null }),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/complete")) {
        return {
          ok: false,
          status: 409,
          statusText: "Conflict",
          json: async () => ({
            error: { code: "http_409", message: "already completed", details: null },
          }),
        } as unknown as Response;
      }
      const result = routeResponse(url, init);
      return { ok: true, status: 200, statusText: "OK", json: async () => result } as unknown as Response;
    }),
  );

  window.history.pushState({}, "", "/review?problem=" + PROBLEM.id);
  render(<ReviewPage />);
  expect(await screen.findByRole("button", { name: /^Easy/ })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /^Easy/ }));

  expect(
    await screen.findByRole("heading", { name: /already completed/i }),
  ).toBeInTheDocument();
  expect(screen.getByText(/scheduler was not advanced twice/i)).toBeInTheDocument();
  window.history.pushState({}, "", "/review");
});

test("API down shows the reachability banner", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      throw new TypeError("network down");
    }),
  );
  // No cached dev user: the bootstrap itself must fail honestly.

  render(<ReviewPage />);
  expect(await screen.findByText(/could not reach the api/i)).toBeInTheDocument();
});
