import "@testing-library/jest-dom/vitest";
import { vi } from "vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// RTL's auto-cleanup depends on global afterEach; we import explicitly,
// so cleanup must be registered by hand.
afterEach(cleanup);

// App-router navigation needs a host context in jsdom tests.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), refresh: vi.fn() }),
  redirect: vi.fn(),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/",
}));
