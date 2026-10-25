/**
 * Same-origin API proxy — catch-all (Phase 6).
 *
 * The browser calls relative `/api/v1/...` paths on the Next.js origin;
 * every `/api/v1/<path>` is forwarded verbatim to
 * `${API_SERVER_URL}/api/v1/<path>`. `/api/v1/health` is a deliberate
 * exception mapped to the backend's liveness endpoint by its own route
 * (see app/api/v1/health/route.ts). Session cookies are therefore
 * first-party; FastAPI still enforces session validation, CSRF tokens,
 * and the forwarded Origin.
 *
 * API_SERVER_URL is server-only env — never exposed to the browser.
 */

import { errorEnvelope, proxyApiRequest } from "@/lib/api-proxy";

export async function proxyCatchAll(request: Request): Promise<Response> {
  const incoming = new URL(request.url);
  if (!incoming.pathname.startsWith("/api/v1/")) {
    return errorEnvelope(404, "proxy_not_found", "Not Found");
  }
  const upstreamPath = `${incoming.pathname}${incoming.search}`;
  return proxyApiRequest(request, upstreamPath);
}

export {
  proxyCatchAll as GET,
  proxyCatchAll as POST,
  proxyCatchAll as PUT,
  proxyCatchAll as PATCH,
  proxyCatchAll as DELETE,
  proxyCatchAll as HEAD,
};
