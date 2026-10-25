/**
 * Explicit same-origin health mapping (Phase 6).
 *
 * The dashboard health indicator polls `/api/v1/health` on THIS origin;
 * the backend's liveness endpoint lives at `/health` (not
 * `/api/v1/health`), so this route forwards to exactly that path and
 * nothing else. GET/HEAD only: health checks are read-only.
 */

import { proxyApiRequest } from "@/lib/api-proxy";

export async function healthProxy(request: Request): Promise<Response> {
  return proxyApiRequest(request, "/health");
}

export { healthProxy as GET, healthProxy as HEAD };
