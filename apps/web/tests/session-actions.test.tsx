/**
 * Session-aware homepage actions (Phase 6). Uses the shared auth harness:
 * session identity comes from /auth/me, and the Codeforces handle state is
 * determined by the existing account-list helper.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";
import { SessionActions } from "../components/home/session-actions";
import {
  clearRoutes,
  setRoute,
  stubAnonSession,
  stubApiDown,
  stubAuthSession,
  stubFetch,
} from "./auth-harness";

const { mockPush } = vi.hoisted(() => ({ mockPush: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, replace: vi.fn() }),
}));

const ACCOUNT = {
  id: "22222222-2222-2222-2222-222222222222",
  handle: "tourist",
  verified_at: null,
  last_synced_at: null,
  last_sync_error: null,
  created_at: "2026-10-25T09:00:00Z",
};

afterEach(() => {
  vi.unstubAllGlobals();
  clearRoutes();
  mockPush.mockClear();
});

describe("SessionActions", () => {
  test("loading: no anonymous or authenticated actions flash", async () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise(() => {}))); // never resolves

    render(<SessionActions />);

    const group = screen.getByRole("group", { name: /account actions/i });
    expect(group).toHaveAttribute("aria-busy", "true");
    expect(screen.queryByRole("link", { name: /^log in$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /get started/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /open dashboard/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /log out/i })).not.toBeInTheDocument();
    expect(screen.getByText(/checking your session/i)).toBeInTheDocument();
  });

  test("anonymous: shows registration and Log in actions only", async () => {
    stubFetch();
    stubAnonSession();

    render(<SessionActions />);

    const getStarted = await screen.findByRole("link", { name: /^get started$/i });
    expect(getStarted).toHaveAttribute("href", "/register");
    const login = screen.getByRole("link", { name: /^log in$/i });
    expect(login).toHaveAttribute("href", "/login");
    expect(screen.queryByRole("link", { name: /open dashboard/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /manage handle/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /log out/i })).not.toBeInTheDocument();
  });

  test("authenticated with a linked handle: dashboard, Manage handle, Review queue, Log out — Log in hidden", async () => {
    stubFetch();
    stubAuthSession();
    setRoute("GET /codeforces/accounts", () => [ACCOUNT]);

    render(<SessionActions />);

    const dashboard = await screen.findByRole("link", { name: /open dashboard/i });
    expect(dashboard).toHaveAttribute("href", "/dashboard");
    const manage = screen.getByRole("link", { name: /manage handle/i });
    expect(manage).toHaveAttribute("href", "/onboarding"); // app route, not Codeforces
    const review = screen.getByRole("link", { name: /review queue/i });
    expect(review).toHaveAttribute("href", "/review");
    expect(screen.getByRole("button", { name: /log out/i })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^log in$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /connect your handle/i })).not.toBeInTheDocument();
  });

  test("authenticated without a handle: Connect your handle instead of Manage handle", async () => {
    stubFetch();
    stubAuthSession();
    setRoute("GET /codeforces/accounts", () => []);

    render(<SessionActions />);

    const connect = await screen.findByRole("link", { name: /connect your handle/i });
    expect(connect).toHaveAttribute("href", "/onboarding");
    const dashboard = screen.getByRole("link", { name: /open dashboard/i });
    expect(dashboard).toHaveAttribute("href", "/dashboard");
    expect(screen.queryByRole("link", { name: /manage handle/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^log in$/i })).not.toBeInTheDocument();
  });

  test("API unreachable: distinct from anonymous — no Log in shown, Retry offered", async () => {
    stubApiDown();

    render(<SessionActions />);

    expect(await screen.findByText(/session status unavailable/i)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^log in$/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /get started/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });

  test("logout calls the logout helper and navigates to the public homepage", async () => {
    stubFetch();
    stubAuthSession();
    setRoute("GET /codeforces/accounts", () => [ACCOUNT]);
    setRoute("POST /auth/logout", () => null);

    render(<SessionActions />);
    await screen.findByRole("link", { name: /open dashboard/i });

    await userEvent.click(screen.getByRole("button", { name: /log out/i }));

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledWith("/");
    });
    // Honest post-logout state: anonymous actions, no authenticated ones.
    expect(await screen.findByRole("link", { name: /^log in$/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /log out/i })).not.toBeInTheDocument();
  });

  test("logout failure reports an error and stays in the authenticated state", async () => {
    stubFetch();
    stubAuthSession();
    setRoute("GET /codeforces/accounts", () => [ACCOUNT]);
    setRoute("POST /auth/logout", () => {
      throw new Error("logout failed upstream");
    });

    render(<SessionActions />);
    await screen.findByRole("link", { name: /open dashboard/i });

    await userEvent.click(screen.getByRole("button", { name: /log out/i }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/log out failed/i)).toBeInTheDocument();
    // Still authenticated: dashboard remains, no anonymous actions injected.
    expect(screen.getByRole("link", { name: /open dashboard/i })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^log in$/i })).not.toBeInTheDocument();
    expect(mockPush).not.toHaveBeenCalled();
  });
});
