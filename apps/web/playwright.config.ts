import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  // Integrated auth specs need a live API; they run via playwright.auth.config.ts.
  testIgnore: "e2e/auth/**",
  timeout: 30_000,
  fullyParallel: true,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL: "http://localhost:3000",
  },
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: {
      // These specs run WITHOUT a live API: the proxy must fail fast (its
      // production wake-retry window would hold the unreachable banner for
      // ~90s). Deployed/integrated runs keep the real window.
      PROXY_TIMEOUT_MS: "50",
      WAKE_RETRY_WINDOW_MS: "2000",
      PROXY_RETRY_DELAY_MS: "100",
    },
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
