import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import OnboardingPage from "../app/onboarding/page";
import { clearRoutes, setRoute, stubAnonSession, stubApiDown, stubAuthSession, stubFetch } from "./auth-harness";

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
  clearRoutes();
});

test("full flow: session bootstrap -> connect handle -> poll to success with solved list", async () => {
  stubFetch();
  stubAuthSession();
  setRoute("GET /codeforces/accounts", () => []);
  setRoute("POST /codeforces/accounts", () => ({ account: ACCOUNT, job: JOB("pending"), queued: false }));
  setRoute("GET /sync-status", () => STATUS("pending"));

  render(<OnboardingPage />);

  const input = await screen.findByLabelText(/codeforces handle/i);
  await userEvent.type(input, "tourist");
  await userEvent.click(screen.getByRole("button", { name: "Connect" }));

  await waitFor(() => {
    // The handle renders as a muted @ plus a mono handle span.
    expect(screen.getByRole("heading", { name: /@tourist/ })).toBeInTheDocument();
  });
  expect(await screen.findByText("pending")).toBeInTheDocument();

  setRoute("GET /sync-status", () => STATUS("succeeded", { submissions: 120, solved_problems: 80 }));
  setRoute("GET /problems", () => ({
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
  }));

  expect(await screen.findByText("succeeded", {}, { timeout: 8000 })).toBeInTheDocument();
  expect(await screen.findByText("80 total", {}, { timeout: 4000 })).toBeInTheDocument();
  expect(screen.getByText(/theatre square/i)).toBeInTheDocument();
  expect(screen.getByText(/solved 2024-05-01/)).toBeInTheDocument();
  expect(screen.getByText("120")).toBeInTheDocument();
});

test("invalid handle shows inline validation without calling the API", async () => {
  stubFetch();
  stubAuthSession();
  setRoute("GET /codeforces/accounts", () => []);

  render(<OnboardingPage />);

  const input = await screen.findByLabelText(/codeforces handle/i);
  await userEvent.type(input, "not a handle!");
  await userEvent.click(screen.getByRole("button", { name: "Connect" }));

  expect(
    await screen.findByText(/1-24 letters, digits, dot, underscore or hyphen/i),
  ).toBeInTheDocument();
});

test("unauthenticated users see the login CTA, never the connect form", async () => {
  stubAnonSession();

  render(<OnboardingPage />);
  const cta = await screen.findByRole("link", { name: /^log in$/i });
  expect(cta).toHaveAttribute("href", "/login");
  expect(screen.queryByLabelText(/codeforces handle/i)).not.toBeInTheDocument();
});

test("API-down bootstrap shows the reachability banner with retry", async () => {
  stubApiDown();

  render(<OnboardingPage />);

  expect(await screen.findByText(/could not reach the api/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
});

test("stale development-mode copy is gone (Phase 5 shipped real auth)", async () => {
  stubFetch();
  stubAuthSession();
  setRoute("GET /codeforces/accounts", () => []);
  setRoute("GET /sync-status", () => STATUS("pending"));

  render(<OnboardingPage />);

  const input = await screen.findByLabelText(/codeforces handle/i);
  expect(input).toBeInTheDocument();
  expect(screen.queryByText(/development mode/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/local dev user/i)).not.toBeInTheDocument();
});

test("failed sync surfaces the error summary", async () => {
  stubFetch();
  stubAuthSession();
  setRoute("GET /codeforces/accounts", () => [ACCOUNT]);
  setRoute("GET /sync-status", () => ({
    account: ACCOUNT,
    latest_jobs: [JOB("failed", { error_summary: "handle not found: tourist" })],
    totals: { submissions: 0, solved_problems: 0 },
  }));

  render(<OnboardingPage />);

  expect(await screen.findByText("failed")).toBeInTheDocument();
  expect(await screen.findByRole("alert")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Sync now" })).toBeInTheDocument();
});
