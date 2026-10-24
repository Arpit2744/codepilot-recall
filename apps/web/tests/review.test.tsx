import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import ReviewPage from "../app/review/page";
import { clearRoutes, setRoute, stubAnonSession, stubApiDown, stubAuthSession, stubFetch } from "./auth-harness";

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

const DUE_ITEM = {
  problem: PROBLEM,
  due_at: "2026-09-20T08:00:00Z",
  last_review_at: "2026-09-10T08:00:00Z",
  repetitions: 3,
  lapses: 1,
  stability: 4.2,
  status: "overdue",
  overdue_seconds: 35 * 86400,
  priority_tier: 1,
  priority_reason:
    "Overdue by 35 days — Critical priority — estimated recall ≈ 42% (model estimate) — low estimated retrievability",
  retrievability: 0.42,
  risk: "high" as const,
};

afterEach(() => {
  vi.unstubAllGlobals();
  clearRoutes();
});

test("empty queue explains honestly; no fabricated reviews", async () => {
  stubFetch();
  stubAuthSession();
  setRoute("GET /reviews/due", () => ({ mode: "due", items: [] }));

  render(<ReviewPage />);
  expect(await screen.findByText(/nothing due right now/i)).toBeInTheDocument();
  expect(
    screen.getByText(/a codeforces acceptance alone never creates a review/i),
  ).toBeInTheDocument();
});

test("due queue lists problems and starts a session with outcome controls", async () => {
  stubFetch();
  stubAuthSession();
  setRoute("GET /reviews/due", () => ({ mode: "due", items: [DUE_ITEM] }));
  setRoute("POST /reviews/sessions", () => ({ session: SESSION, problem: PROBLEM, memory: null }));

  render(<ReviewPage />);
  expect(await screen.findByText(/Theatre Square/)).toBeInTheDocument();

  expect(screen.getByText("Overdue")).toBeInTheDocument();
  expect(screen.getByText("Critical priority")).toBeInTheDocument();
  expect(screen.getByText(/Overdue by 35 days/)).toBeInTheDocument();
  expect(screen.getByText(/estimated recall ≈ 42% \(high risk\)/)).toBeInTheDocument();

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

test("unavailable estimates are labeled, never invented", async () => {
  stubFetch();
  stubAuthSession();
  setRoute("GET /reviews/due", () => ({
    mode: "due",
    items: [
      {
        ...DUE_ITEM,
        retrievability: null,
        risk: null,
        priority_reason: "Overdue by 35 days — Critical priority",
      },
    ],
  }));

  render(<ReviewPage />);
  expect(await screen.findByText(/recall estimate unavailable/i)).toBeInTheDocument();
});

test("upcoming mode is clearly typed and separate", async () => {
  stubFetch();
  stubAuthSession();
  setRoute("GET /reviews/due", (url) =>
    url.includes("mode=upcoming")
      ? {
          mode: "upcoming",
          items: [
            {
              problem: PROBLEM,
              due_at: "2026-10-25T18:00:00Z",
              last_review_at: "2026-10-24T12:00:00Z",
              repetitions: 1,
              lapses: 0,
              stability: 2.3,
              status: "upcoming" as const,
              seconds_until_due: 6 * 3600,
              priority_tier: null,
              priority_reason: "Scheduled in 6 hours",
              retrievability: null,
              risk: null,
            },
          ],
        }
      : { mode: "due", items: [] },
  );

  render(<ReviewPage />);
  expect(await screen.findByText(/nothing due right now/i)).toBeInTheDocument();

  await userEvent.click(screen.getByRole("tab", { name: "Upcoming" }));
  expect(await screen.findByText("Upcoming reviews")).toBeInTheDocument();
  expect(screen.getByText("Scheduled in 6 hours")).toBeInTheDocument();
});

test("successful completion shows only the backend-confirmed next due date", async () => {
  stubFetch();
  stubAuthSession();
  setRoute("GET /reviews/due", () => ({ mode: "due", items: [] }));
  setRoute("POST /reviews/sessions", () => ({ session: SESSION, problem: PROBLEM, memory: null }));
  setRoute("POST /complete", () => ({
    session: {
      ...SESSION,
      status: "completed",
      outcome: "good",
      independent: true,
      help_level: "none",
    },
    problem: PROBLEM,
    memory: MEMORY,
  }));

  window.history.pushState({}, "", "/review?problem=" + PROBLEM.id);
  render(<ReviewPage />);
  expect(await screen.findByRole("button", { name: /^Good/ })).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: /^Good/ }));

  expect(await screen.findByText(/review recorded/i)).toBeInTheDocument();
  expect(screen.getByText(/2026-11-05 12:00 UTC/i)).toBeInTheDocument();
  expect(screen.getByText(/fsrs-6\.3\.2/i)).toBeInTheDocument();
  window.history.pushState({}, "", "/review");
});

test("409 conflict shows already-completed state", async () => {
  stubFetch();
  stubAuthSession();
  setRoute("GET /reviews/due", () => ({ mode: "due", items: [] }));
  setRoute("POST /reviews/sessions", () => ({ session: SESSION, problem: PROBLEM, memory: null }));
  setRoute("POST /complete", () => ({
    error: { code: "http_409", message: "already completed", details: null },
  }));
  // The complete route must return a 409 response shape — emulate via fetch:
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
            error: { code: "http_409", message: "Review session is already completed", details: null },
          }),
        } as unknown as Response;
      }
      const path = url.split("?")[0];
      const method = (init?.method ?? "GET").toUpperCase();
      if (path.endsWith("/auth/me")) {
        return { ok: true, status: 200, statusText: "OK", json: async () => ({}) } as unknown as Response;
      }
      if (path.endsWith("/reviews/sessions") && method === "POST") {
        return {
          ok: true,
          status: 201,
          statusText: "Created",
          json: async () => ({ session: SESSION, problem: PROBLEM, memory: null }),
        } as unknown as Response;
      }
      return {
        ok: true,
        status: 200,
        statusText: "OK",
        json: async () => ({ mode: "due", items: [] }),
      } as unknown as Response;
    }),
  );

  window.history.pushState({}, "", "/review?problem=" + PROBLEM.id);
  render(<ReviewPage />);
  expect(await screen.findByRole("button", { name: /^Easy/ })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /^Easy/ }));

  expect(
    await screen.findByRole("heading", { name: /already completed/i }),
  ).toBeInTheDocument();
  window.history.pushState({}, "", "/review");
});

test("unauthenticated users see the login CTA", async () => {
  stubAnonSession();

  render(<ReviewPage />);
  const cta = await screen.findByRole("link", { name: /^log in$/i });
  expect(cta).toHaveAttribute("href", "/login");
});

test("API down shows the reachability banner", async () => {
  stubApiDown();

  render(<ReviewPage />);
  expect(await screen.findByText(/could not reach the api/i)).toBeInTheDocument();
});
