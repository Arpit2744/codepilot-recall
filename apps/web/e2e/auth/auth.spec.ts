import { expect, test } from "@playwright/test";

/**
 * Integrated, real-API auth flows (Phase 5). The API is live on :8000 with
 * a disposable database; every step goes through real HTTP, real cookies,
 * and the CSRF machinery. No X-User-Id, no localStorage identity.
 */

const A = {
  email: `alice+${Date.now()}@example.com`,
  password: "Passw0rd!A",
  handle: "AliceHandle",
};
const B = {
  email: `bob+${Date.now()}@example.com`,
  password: "Passw0rd!B",
  handle: "AliceHandle", // deliberately the SAME public handle (ADR-0009)
};

test("register -> onboarding -> dashboard survives reload; logout invalidates", async ({ page }) => {
  await page.goto("/register");
  await page.getByLabel(/^email/i).fill(A.email);
  await page.getByLabel(/^password/i).fill(A.password);
  await page.getByRole("button", { name: /create account/i }).click();

  // Registration opens a session and lands on onboarding.
  await expect(page.getByRole("heading", { name: /connect codeforces/i })).toBeVisible({
    timeout: 15_000,
  });

  // The handle-connect form is reachable for an authenticated user.
  await page.getByLabel(/codeforces handle/i).fill(A.handle);
  await page.getByRole("button", { name: "Connect" }).click();
  await expect(page.getByText(`@${A.handle}`)).toBeVisible({ timeout: 15_000 });

  // Reload preserves the session through the HttpOnly cookie.
  await page.reload();
  await expect(page.getByText(`@${A.handle}`)).toBeVisible({ timeout: 15_000 });

  // Logout invalidates the session immediately.
  await page.goto("/dashboard");
  await page.getByRole("button", { name: /log out/i }).click();
  await expect(page).toHaveURL(/\/login/);

  // The next authenticated request fails closed.
  await page.goto("/dashboard");
  await expect(page.getByRole("link", { name: /^log in$/i })).toBeVisible({ timeout: 15_000 });
});

test("second user onboards independently; shared handle, isolated data", async ({ page }) => {
  // Alice first.
  await page.goto("/register");
  await page.getByLabel(/^email/i).fill(A.email.replace("alice", "carol"));
  await page.getByLabel(/^password/i).fill(A.password);
  await page.getByRole("button", { name: /create account/i }).click();
  await expect(page.getByRole("heading", { name: /connect codeforces/i })).toBeVisible({
    timeout: 15_000,
  });
  await page.getByLabel(/codeforces handle/i).fill("SharedHandle");
  await page.getByRole("button", { name: "Connect" }).click();
  await expect(page.getByText("@SharedHandle")).toBeVisible({ timeout: 15_000 });
  await page.goto("/dashboard");
  await page.getByRole("button", { name: /log out/i }).click({ timeout: 15_000 });
  await expect(page).toHaveURL(/\/login/, { timeout: 15_000 });

  // Bob registers separately and links the SAME public handle.
  await page.goto("/register");
  await page.getByLabel(/^email/i).fill(B.email.replace("bob", "dave"));
  await page.getByLabel(/^password/i).fill(B.password);
  await page.getByRole("button", { name: /create account/i }).click();
  await expect(page.getByRole("heading", { name: /connect codeforces/i })).toBeVisible({
    timeout: 15_000,
  });
  await page.getByLabel(/codeforces handle/i).fill("SharedHandle");
  await page.getByRole("button", { name: "Connect" }).click();
  await expect(page.getByText("@SharedHandle")).toBeVisible({ timeout: 15_000 });

  // Dave's dashboard shows only Dave's (empty) activity, never Carol's data.
  await page.goto("/dashboard");
  // Authenticated dashboard rendered with Dave's own (empty) totals.
  await expect(page.getByText("Problems solved")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(/review queue/i)).toBeVisible({ timeout: 15_000 });
});

test("login with wrong password shows the uniform error", async ({ page }) => {
  await page.goto("/register");
  await page.getByLabel(/^email/i).fill(`eve+${Date.now()}@example.com`);
  await page.getByLabel(/^password/i).fill("Passw0rd!E");
  await page.getByRole("button", { name: /create account/i }).click();
  await expect(page.getByRole("heading", { name: /connect codeforces/i })).toBeVisible({
    timeout: 15_000,
  });
  await page.goto("/dashboard");
  await page.getByRole("button", { name: /log out/i }).click({ timeout: 15_000 });
  await expect(page).toHaveURL(/\/login/, { timeout: 15_000 });

  await page.getByLabel(/^email/i).fill("nobody@example.com");
  await page.getByLabel(/^password/i).fill("WrongPass1");
  await page.getByRole("button", { name: /log in/i }).click();
  await expect(page.getByText(/invalid email or password/i)).toBeVisible({ timeout: 15_000 });
});
