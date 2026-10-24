import { expect, test } from "@playwright/test";

/** No backend in e2e: the review page must degrade honestly. */
test("review page reports unreachable API without fake data", async ({ page }) => {
  await page.goto("/review");

  await expect(page.getByRole("heading", { name: "Review" })).toBeVisible();
  await expect(page.getByText(/could not reach the api/i)).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
});

test("dashboard links to the review queue", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page.getByRole("link", { name: /review queue/i })).toHaveAttribute(
    "href",
    "/review",
  );
});
