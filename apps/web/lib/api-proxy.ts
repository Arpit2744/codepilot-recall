/**
 * Server-only API proxy core (Phase 6).
 *
 * Shared by the catch-all route (`/api/v1/*` → same path upstream) and the
 * explicit health mapping (`/api/v1/health` → backend `/health`). Browser
 * requests hit the Next.js origin; this module forwards server-side to
 * `API_SERVER_URL` so session cookies stay first-party. FastAPI still
 * enforces session validation, CSRF tokens, and the forwarded Origin.
 *
 * Never imported by client code: API_SERVER_URL is server-only.
 */

const API_SERVER_URL = (process.env.API_SERVER_URL ?? "http://127.0.0.1:8000").replace(
  /\/+$/,
  "",
);

/** Per-attempt upstream timeout: a delivered request that stalls. */
const PROXY_TIMEOUT_MS = Number(process.env.PROXY_TIMEOUT_MS ?? 20_000);
/** Total budget for waking a sleeping free-tier service. */
const WAKE_RETRY_WINDOW_MS = Number(process.env.WAKE_RETRY_WINDOW_MS ?? 90_000);
const PROXY_RETRY_DELAY_MS = Number(process.env.PROXY_RETRY_DELAY_MS ?? 2_000);

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

function isAbortError(err: unknown): boolean {
  if (typeof err !== "object" || err === null) return false;
  const name = (err as { name?: string }).name;
  return name === "AbortError" || name === "TimeoutError";
}

/** Hop-by-hop and identity headers that must not be forwarded verbatim. */
const SKIPPED_REQUEST_HEADERS = new Set([
  "host",
  "content-length",
  "connection",
  "keep-alive",
  "transfer-encoding",
  "upgrade",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "accept-encoding",
]);

const SKIPPED_RESPONSE_HEADERS = new Set([
  "content-length",
  "connection",
  "keep-alive",
  "transfer-encoding",
  "content-encoding",
  "set-cookie", // handled explicitly below (multi-valued)
]);

function collectSetCookie(headers: Headers): string[] {
  const withCast = headers as Headers & { getSetCookie?: () => string[] };
  if (typeof withCast.getSetCookie === "function") {
    return withCast.getSetCookie();
  }
  const raw = headers.get("set-cookie");
  return raw ? [raw] : [];
}

export function errorEnvelope(status: number, code: string, message: string): Response {
  return Response.json(
    { error: { code, message, details: null } },
    { status, headers: { "cache-control": "no-store" } },
  );
}

/**
 * Forward `request` to `${API_SERVER_URL}${upstreamPath}`.
 *
 * Cold-start safety: connection-phase failures prove the request was never
 * delivered, so EVERY method retries within the wake window. A timeout
 * means the request MAY have been delivered: idempotent GET/HEAD may
 * retry, but mutations return an honest 504 immediately so a timed-out
 * registration can never be replayed into a duplicate.
 */
export async function proxyApiRequest(
  request: Request,
  upstreamPath: string,
): Promise<Response> {
  const target = `${API_SERVER_URL}${upstreamPath}`;

  const headers = new Headers();
  for (const [name, value] of request.headers.entries()) {
    if (!SKIPPED_REQUEST_HEADERS.has(name)) {
      headers.set(name, value);
    }
  }

  const method = request.method.toUpperCase();
  const init: RequestInit = {
    method,
    headers,
    redirect: "manual",
  };
  if (method !== "GET" && method !== "HEAD") {
    init.body = await request.arrayBuffer();
  }

  const wakeDeadline = Date.now() + WAKE_RETRY_WINDOW_MS;
  let upstream: Response;
  for (;;) {
    try {
      upstream = await fetch(target, {
        ...init,
        signal: AbortSignal.timeout(PROXY_TIMEOUT_MS),
      });
      break;
    } catch (err) {
      if (isAbortError(err)) {
        // Delivered-or-unknown: only idempotent methods may retry.
        if ((method === "GET" || method === "HEAD") && Date.now() < wakeDeadline) {
          await sleep(PROXY_RETRY_DELAY_MS);
          continue;
        }
        return errorEnvelope(
          504,
          "api_timeout",
          "The API service did not respond in time. If you were submitting something, check whether it succeeded before trying again.",
        );
      }
      // Connection-phase failure: the request was never delivered, so
      // retrying every method cannot duplicate work (this is what makes a
      // sleeping service wake up safely, even for registrations).
      if (Date.now() + PROXY_TIMEOUT_MS < wakeDeadline) {
        await sleep(PROXY_RETRY_DELAY_MS);
        continue;
      }
      return errorEnvelope(
        502,
        "api_unreachable",
        "The API service is temporarily unreachable. It may be waking up — retry shortly.",
      );
    }
  }

  const responseHeaders = new Headers();
  for (const [name, value] of upstream.headers.entries()) {
    if (!SKIPPED_RESPONSE_HEADERS.has(name)) {
      responseHeaders.set(name, value);
    }
  }
  const response = new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  });
  // Multi-valued Set-Cookie must be appended, not joined.
  for (const cookie of collectSetCookie(upstream.headers)) {
    response.headers.append("set-cookie", cookie);
  }
  return response;
}
