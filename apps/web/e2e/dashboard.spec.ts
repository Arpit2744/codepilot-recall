import { expect, test } from "@playwright/test";

/**
 * Runs against `npm run dev` with NO backend: the dashboard must degrade to
 * honest reachability states — never fabricated numbers.
 */
test("dashboard reports unreachable API without fake data", async ({ page }) => {
  await page.goto("/dashboard");

  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();

  await expect(page.getByText(/could not reach the api/i)).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
  // No summary numbers may render while the API is unreachable.
  await expect(page.getByText("421")).toHaveCount(0);
});

test("landing page does not claim authenticated actions without a session", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("link", { name: /how it works/i })).toBeVisible();
  await expect(page.getByText(/session status unavailable/i)).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.getByRole("link", { name: /open dashboard/i })).toHaveCount(0);
});
