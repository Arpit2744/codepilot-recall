import { defineConfig, devices } from "@playwright/test";

/**
 * INTEGRATED auth E2E: expects the real API on 127.0.0.1:8000 (started by
 * CI or the developer; SQLite or PostgreSQL behind it) and boots the Next
 * dev server itself. Covers register → login → dashboard → logout and
 * two-user isolation through real HTTP + real cookies + real CSRF.
 */
export default defineConfig({
  testDir: "./e2e/auth",
  timeout: 60_000,
  fullyParallel: false, // shared dev server + sequential user scenarios
  retries: 0,
  reporter: "list",
  use: {
    baseURL: "http://localhost:3000",
  },
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: true,
    timeout: 120_000,
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
