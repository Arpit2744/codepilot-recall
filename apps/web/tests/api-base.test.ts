// @vitest-environment node
/**
 * Regression tests (Phase 6): the production frontend build must default to
 * RELATIVE API paths (same-origin proxy), never a baked-in localhost
 * origin. The Dockerfile's NEXT_PUBLIC_API_BASE_URL ARG defaults to "" and
 * docker-compose explicitly supplies http://localhost:8000 for local
 * development — both behaviors are pinned here.
 */
import { afterEach, describe, expect, test, vi } from "vitest";

async function loadApiBase(buildTimeValue: string | undefined): Promise<string> {
  vi.resetModules();
  if (buildTimeValue === undefined) {
    // Truly absent from the build environment (Docker ARG not provided).
    delete process.env.NEXT_PUBLIC_API_BASE_URL;
  } else {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", buildTimeValue);
  }
  const mod = await import("../lib/api");
  return mod.API_BASE_URL;
}

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("client API base URL", () => {
  test("unset build-time value → relative paths (Dockerfile default)", async () => {
    expect(await loadApiBase(undefined)).toBe("");
  });

  test("empty build-time value → relative paths (Docker ARG='')", async () => {
    expect(await loadApiBase("")).toBe("");
  });

  test("explicit localhost preserved for non-proxy local development", async () => {
    expect(await loadApiBase("http://localhost:8000")).toBe(
      "http://localhost:8000",
    );
  });

  test("localhost is never chosen as a fallback", async () => {
    // The pre-Phase-6 default leaked into visitor browsers; this pins the fix.
    expect(await loadApiBase(undefined)).not.toContain("localhost");
  });
});
