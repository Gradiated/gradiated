import { randomUUID } from "node:crypto";

import { expect, readMagicLink, test } from "./fixtures";

test("sign-in page sends and consumes a magic link", async ({
  account,
  context,
  page,
}) => {
  await context.clearCookies();
  await page.goto("/api-keys");
  await expect(page).toHaveURL(/\/login$/);

  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await page.getByLabel("Email").fill(account.email);
  await page.getByRole("button", { name: "Email me a sign-in link" }).click();
  await expect(page.getByText("Check your email")).toBeVisible();

  const verification = await readMagicLink(context.request, account.email);
  await page.goto(verification.toString());

  await expect(page).toHaveURL(/\/api-keys$/);
  await expect(
    page.getByRole("heading", { level: 1, name: "API keys", exact: true }),
  ).toBeVisible();
});

test("signed-in navigation includes training and sign out returns to login", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/api-keys$/);

  await page.goto("/tasks");
  await expect(page).toHaveURL(/\/tasks$/);
  await expect(
    page.getByRole("heading", { level: 1, name: "Training" }),
  ).toBeVisible();

  const navigation = page.locator('[data-sidebar="content"]');
  await expect(
    navigation.getByRole("link", { name: "Training", exact: true }),
  ).toBeVisible();
  await expect(
    navigation.getByRole("link", { name: "Training" }),
  ).toHaveAttribute("data-active", "true");
  await expect(
    navigation.getByRole("link", { name: "Models" }),
  ).toHaveAttribute("data-active", "false");
  await expect(
    navigation.getByRole("link", { name: "API keys" }),
  ).toHaveAttribute("data-active", "false");

  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);

  await page.goto("/api-keys");
  await expect(page).toHaveURL(/\/login$/);
});

test("a stale saved selection falls back to the account's own workspace", async ({
  account,
  page,
}) => {
  const staleSelection = JSON.stringify({
    state: { organizationId: randomUUID(), workspaceId: randomUUID() },
    version: 0,
  });
  await page.addInitScript((selection) => {
    window.localStorage.setItem("gradiated-workspace-selection", selection);
  }, staleSelection);

  const failedApiRequests: string[] = [];
  page.on("response", (response) => {
    if (response.url().includes("/api/v1/") && response.status() >= 400) {
      failedApiRequests.push(`${response.status()} ${response.url()}`);
    }
  });

  await page.goto("/api-keys");
  const workspaceMenu = page.getByRole("button", { name: "Workspace menu" });
  await expect(workspaceMenu).toContainText("Default");
  await expect(
    page.getByRole("button", { name: "Account menu" }),
  ).toContainText(account.userName);
  expect(failedApiRequests).toEqual([]);
});

test("a failed account load retries, then recovers on Retry", async ({
  page,
}) => {
  let meRequests = 0;
  await page.route("**/api/v1/me", (route) => {
    meRequests += 1;
    return route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ detail: "unavailable" }),
    });
  });
  await page.clock.install();
  await page.goto("/api-keys");

  const retry = page.getByRole("button", { name: "Retry" });
  await expect(async () => {
    await page.clock.fastForward(1_000);
    await expect(retry).toBeVisible({ timeout: 100 });
  }).toPass();
  expect(meRequests).toBe(4);
  await expect(page.getByRole("button", { name: "Account menu" })).toHaveCount(
    0,
  );

  await page.unroute("**/api/v1/me");
  await retry.click();
  await expect(
    page.getByRole("button", { name: "Workspace menu" }),
  ).toContainText("Default");
});

test("a failed workspace load offers Retry, then recovers", async ({
  page,
}) => {
  const workspacesRoute = "**/api/v1/organizations/*/workspaces";
  await page.route(workspacesRoute, (route) =>
    route.request().method() === "GET"
      ? route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ detail: "unavailable" }),
        })
      : route.fallback(),
  );
  await page.clock.install();
  await page.goto("/api-keys");

  const retry = page.getByRole("button", { name: "Retry" });
  await expect(async () => {
    await page.clock.fastForward(1_000);
    await expect(retry).toBeVisible({ timeout: 100 });
  }).toPass();

  await page.unroute(workspacesRoute);
  await retry.click();
  await expect(
    page.getByRole("button", { name: "Workspace menu" }),
  ).toContainText("Default");
});

test("a failed sign-out keeps the session", async ({ page }) => {
  await page.goto("/api-keys");
  await page.route("**/api/auth/sign-out", (route) =>
    route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ message: "unavailable" }),
    }),
  );

  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  const retry = page.getByRole("menuitem", { name: "Sign out failed. Retry" });
  await expect(retry).toBeVisible();
  await expect(page).toHaveURL(/\/api-keys$/);

  await page.unroute("**/api/auth/sign-out");
  await retry.click();
  await expect(page).toHaveURL(/\/login$/);
});

test("a sign-out network failure keeps the session", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/api-keys");
  await page.route("**/api/auth/sign-out", (route) => route.abort());

  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await expect(
    page.getByRole("menuitem", { name: "Sign out failed. Retry" }),
  ).toBeVisible();
  await expect(page).toHaveURL(/\/api-keys$/);
  expect(errors).toEqual([]);
});

test("a sign-in network failure shows an error and re-enables sign-in", async ({
  context,
  page,
}) => {
  await context.clearCookies();
  await page.route("**/api/auth/sign-in/social", (route) => route.abort());
  await page.goto("/login");

  await page.getByRole("button", { name: "Continue with GitHub" }).click();

  await expect(
    page.getByText("GitHub sign-in could not start. Try again."),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Continue with Google" }),
  ).toBeEnabled();
  await expect(
    page.getByRole("button", { name: "Email me a sign-in link" }),
  ).toBeEnabled();
});
