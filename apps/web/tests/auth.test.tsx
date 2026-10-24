import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import LoginPage from "../app/login/page";
import RegisterPage from "../app/register/page";

afterEach(() => {
  vi.unstubAllGlobals();
});

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status < 400,
    status,
    statusText: "OK",
    json: async () => body,
  } as unknown as Response;
}

test("login submits credentials and routes to the dashboard", async () => {
  const calls: Array<[string, RequestInit | undefined]> = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      calls.push([String(input), init]);
      return jsonResponse({
        user: { id: "u1", email: "dev@example.com", display_name: "Dev", created_at: "x" },
        csrf_token: "tok",
      });
    }),
  );

  render(<LoginPage />);
  await userEvent.type(screen.getByLabelText(/email/i), "dev@example.com");
  await userEvent.type(screen.getByLabelText(/password/i), "Passw0rd!");
  await userEvent.click(screen.getByRole("button", { name: /log in/i }));

  await vi.waitFor(() => {
    const loginCall = calls.find(([url]) => url.includes("/api/v1/auth/login"));
    expect(loginCall).toBeDefined();
    const init = loginCall![1];
    expect((init?.body as string)).toContain("dev@example.com");
    expect(init?.credentials).toBe("include"); // cookie session
    // CSRF bootstrap fires first (apiFetch auto-acquire), never a bearer token.
    expect(calls[0][0]).toContain("/api/v1/auth/csrf");
  });
});

test("login shows the uniform 401 message without enumeration detail", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      jsonResponse(
        { error: { code: "http_401", message: "Invalid email or password.", details: null } },
        401,
      ),
    ),
  );

  render(<LoginPage />);
  await userEvent.type(screen.getByLabelText(/email/i), "ghost@example.com");
  await userEvent.type(screen.getByLabelText(/password/i), "Whatever1");
  await userEvent.click(screen.getByRole("button", { name: /log in/i }));

  expect(await screen.findByText(/invalid email or password/i)).toBeInTheDocument();
});

test("login shows rate-limit guidance on 429", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      jsonResponse(
        { error: { code: "http_429", message: "Too many attempts", details: null } },
        429,
      ),
    ),
  );

  render(<LoginPage />);
  await userEvent.type(screen.getByLabelText(/email/i), "dev@example.com");
  await userEvent.type(screen.getByLabelText(/password/i), "Passw0rd!");
  await userEvent.click(screen.getByRole("button", { name: /log in/i }));

  expect(await screen.findByText(/too many attempts/i)).toBeInTheDocument();
});

test("register validates password shape before any request", async () => {
  const fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);

  render(<RegisterPage />);
  await userEvent.type(screen.getByLabelText(/^email/i), "new@example.com");
  await userEvent.type(screen.getByLabelText(/password/i), "short");
  await userEvent.click(screen.getByRole("button", { name: /create account/i }));

  expect(await screen.findByText(/^password needs at least 8 characters/i)).toBeInTheDocument();
  expect(fetchMock).not.toHaveBeenCalled();
});

test("register surfaces duplicate-account conflict safely", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      jsonResponse(
        {
          error: {
            code: "http_409",
            message: "An account with this email already exists",
            details: null,
          },
        },
        409,
      ),
    ),
  );

  render(<RegisterPage />);
  await userEvent.type(screen.getByLabelText(/^email/i), "taken@example.com");
  await userEvent.type(screen.getByLabelText(/password/i), "Passw0rd!");
  await userEvent.click(screen.getByRole("button", { name: /create account/i }));

  expect(await screen.findByText(/already exists/i)).toBeInTheDocument();
});

test("register API-down shows the reachability message", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      throw new TypeError("network down");
    }),
  );

  render(<RegisterPage />);
  await userEvent.type(screen.getByLabelText(/^email/i), "x@example.com");
  await userEvent.type(screen.getByLabelText(/password/i), "Passw0rd!");
  await userEvent.click(screen.getByRole("button", { name: /create account/i }));

  expect(await screen.findByText(/could not reach the api/i)).toBeInTheDocument();
});
