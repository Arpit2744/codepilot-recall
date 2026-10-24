import { expect, test } from "@playwright/test";

test("landing page renders hero and features", async ({ page }) => {
  await page.goto("/");

  await expect(
    page.getByRole("heading", { level: 1, name: /remember every problem/i }),
  ).toBeVisible();

  await expect(page.getByText("True first-solve dates")).toBeVisible();
  await expect(page.getByText("Adaptive revision")).toBeVisible();
});

test("api status indicator settles into a terminal state", async ({ page }) => {
  await page.goto("/");

  // Whether the API is up or down, the pill must leave the loading state.
  await expect(
    page
      .getByRole("status")
      .filter({ hasText: /API online|API unreachable/ }),
  ).toBeVisible({ timeout: 15_000 });
});
