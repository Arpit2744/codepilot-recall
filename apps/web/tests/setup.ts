import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// RTL's auto-cleanup depends on global afterEach; we import explicitly,
// so cleanup must be registered by hand.
afterEach(cleanup);
