import { expect, test } from "@playwright/test";

/**
 * Runs against `npm run dev` with NO backend running: verifies the UI
 survives an unreachable API with honest, actionable states — never fake data.
 */
test("onboarding page renders and reports an unreachable API", async ({ page }) => {
  await page.goto("/onboarding");

  await expect(
    page.getByRole("heading", { name: /connect codeforces/i }),
  ).toBeVisible();

  // No backend: the dev-session banner must surface a retry affordance.
  await expect(
    page.getByText(/could not reach the api to start a local session/i),
  ).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
});

test("landing page links to onboarding", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("link", { name: /connect your handle/i })).toHaveAttribute(
    "href",
    "/onboarding",
  );
});
