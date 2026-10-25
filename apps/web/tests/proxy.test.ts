// @vitest-environment node
/**
 * Same-origin API proxy tests (Phase 6). The handler is exercised with
 * plain Requests against a stubbed server-side fetch: cookie forwarding,
 * CSRF header forwarding, Set-Cookie propagation (multi-valued), error
 * envelopes, and method/body handling.
 */
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

let upstream: Response | Error;
let captured: { url: string; init: RequestInit | undefined } | null = null;

async function handler(request: Request): Promise<Response> {
  const mod = await import("../app/api/v1/[...path]/route");
  return mod.GET(request);
}

/** Reload the route module with small deterministic retry knobs. */
async function handlerWithRetries(): Promise<{
  GET: (request: Request) => Promise<Response>;
}> {
  vi.resetModules();
  vi.stubEnv("PROXY_TIMEOUT_MS", "50");
  vi.stubEnv("WAKE_RETRY_WINDOW_MS", "400");
  vi.stubEnv("PROXY_RETRY_DELAY_MS", "10");
  return import("../app/api/v1/[...path]/route");
}

function connectionError(): Error {
  return Object.assign(new Error("fetch failed"), { name: "TypeError" });
}

function timeoutError(): Error {
  return Object.assign(new Error("timed out"), { name: "TimeoutError" });
}

let fetchCalls: number;

function stubFailingFetch(sequence: Array<Error | Response>) {
  fetchCalls = 0;
  const queue = [...sequence];
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      fetchCalls += 1;
      const next = queue.shift();
      if (next instanceof Error) throw next;
      return next ?? new Response("{}", { status: 200 });
    }),
  );
}

function proxyRequest(
  path: string,
  init?: RequestInit & { origin?: string },
): Request {
  const headers = new Headers(init?.headers);
  if (init?.origin) headers.set("origin", init.origin);
  return new Request(`https://web.example${path}`, {
    method: init?.method ?? "GET",
    headers,
    body: init?.body,
  });
}

beforeEach(() => {
  upstream = new Response("{}", { status: 200 });
  captured = null;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      captured = { url: String(input), init };
      if (upstream instanceof Error) throw upstream;
      return upstream;
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api proxy", () => {
  test("forwards method, path, query, cookies, and csrf header upstream", async () => {
    upstream = new Response("{}", { status: 200 });
    await handler(
      proxyRequest("/api/v1/codeforces/accounts?page=2", {
        method: "POST",
        headers: {
          cookie: "cpr_session=abc; other=x",
          "x-csrf-token": "tok-1",
          "content-type": "application/json",
        },
        body: JSON.stringify({ handle: "tourist" }),
      }),
    );

    expect(captured?.url).toBe(
      "http://127.0.0.1:8000/api/v1/codeforces/accounts?page=2",
    );
    const headers = new Headers(captured?.init?.headers);
    expect(headers.get("cookie")).toBe("cpr_session=abc; other=x");
    expect(headers.get("x-csrf-token")).toBe("tok-1");
    expect(headers.get("content-type")).toContain("application/json");
    expect(headers.get("host")).toBeNull(); // identity header not forwarded
    expect(captured?.init?.method).toBe("POST");
    const bodyText = new TextDecoder().decode(captured?.init?.body as ArrayBuffer);
    expect(bodyText).toContain("tourist");
  });

  test("propagates upstream status, body, and multiple Set-Cookie headers", async () => {
    upstream = new Response(JSON.stringify({ ok: true }), {
      status: 201,
      headers: new Headers([
        ["content-type", "application/json"],
        ["set-cookie", "cpr_session=abc; Path=/; HttpOnly; SameSite=Lax"],
        ["set-cookie", "second=1; Path=/"],
      ]),
    });

    const response = await handler(
      proxyRequest("/api/v1/auth/login", { method: "POST" }),
    );

    expect(response.status).toBe(201);
    expect(await response.json()).toEqual({ ok: true });
    const cookies = response.headers.getSetCookie();
    expect(cookies).toHaveLength(2);
    expect(cookies[0]).toContain("cpr_session=abc");
    expect(response.headers.get("content-length")).toBeNull();
  });

  test("maps upstream failure to the standard error envelope with honest status", async () => {
    upstream = new Response(
      JSON.stringify({ error: { code: "http_409", message: "conflict", details: null } }),
      { status: 409, headers: { "content-type": "application/json" } },
    );

    const response = await handler(proxyRequest("/api/v1/codeforces/accounts", { method: "POST" }));

    expect(response.status).toBe(409);
    const body = await response.json();
    expect(body.error.code).toBe("http_409");
  });

  test("returns a 502 envelope when the API is unreachable — never fake data", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw connectionError();
      }),
    );
    const mod = await handlerWithRetries();

    const response = await mod.GET(proxyRequest("/api/v1/dashboard/summary"));

    expect(response.status).toBe(502);
    const body = await response.json();
    expect(body.error.code).toBe("api_unreachable");
    expect(body.error.message).toContain("unreachable");
  });

  test("non-/api/v1 paths are not proxied", async () => {
    const response = await handler(proxyRequest("/api/other"));
    expect(response.status).toBe(404);
    expect(captured).toBeNull();
  });

  test("cold start: connection failure retries POST (request never delivered)", async () => {
    stubFailingFetch([connectionError(), connectionError(), new Response("{}", { status: 201 })]);
    const mod = await handlerWithRetries();

    const response = await mod.GET(
      proxyRequest("/api/v1/codeforces/accounts", {
        method: "POST",
        body: JSON.stringify({ handle: "tourist" }),
      }),
    );

    expect(response.status).toBe(201);
    expect(fetchCalls).toBe(3); // retried safely: never delivered upstream
  });

  test("cold start exhausted: connection failures end in 502", async () => {
    stubFailingFetch(Array.from({ length: 50 }, () => connectionError()));
    const mod = await handlerWithRetries();

    const response = await mod.GET(proxyRequest("/api/v1/dashboard/summary"));

    expect(response.status).toBe(502);
    const body = await response.json();
    expect(body.error.code).toBe("api_unreachable");
    expect(fetchCalls).toBeGreaterThan(1);
  });

  test("timeout on GET retries within the wake window", async () => {
    stubFailingFetch([timeoutError(), new Response("{}", { status: 200 })]);
    const mod = await handlerWithRetries();

    const response = await mod.GET(proxyRequest("/api/v1/dashboard/summary"));

    expect(response.status).toBe(200);
    expect(fetchCalls).toBe(2);
  });

  test("timeout on POST returns 504 without retry — no duplicate registration", async () => {
    stubFailingFetch([timeoutError()]);
    const mod = await handlerWithRetries();

    const response = await mod.GET(
      proxyRequest("/api/v1/auth/register", {
        method: "POST",
        body: JSON.stringify({ email: "a@b.c", password: "Passw0rd!" }),
      }),
    );

    expect(response.status).toBe(504);
    expect(fetchCalls).toBe(1); // delivered-or-unknown: never replayed
    const body = await response.json();
    expect(body.error.code).toBe("api_timeout");
  });

  test("honors API_SERVER_URL when configured", async () => {
    vi.resetModules();
    vi.stubEnv("API_SERVER_URL", "https://api.example.com/");
    upstream = new Response("{}", { status: 200 });

    const mod = await import("../app/api/v1/[...path]/route");
    await mod.GET(proxyRequest("/api/v1/health"));

    expect(captured?.url).toBe("https://api.example.com/api/v1/health");
    vi.unstubAllEnvs();
  });
});
