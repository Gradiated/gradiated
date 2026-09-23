import type { Page } from "@playwright/test";

import { expect, test } from "./fixtures";
import { apiPathEndsWith, fulfillJson, fulfillProblem } from "./routes";

const createKey = async (page: Page, name: string) => {
  await page.getByRole("button", { name: "Create API key" }).click();
  await page.getByLabel("Name").fill(name);
  await page.getByRole("button", { name: "Create key" }).click();

  await expect(
    page.getByRole("heading", { name: "Copy your API key" }),
  ).toBeVisible();
  await expect(page.getByTestId("api-key-secret")).toHaveText(
    /^grad_[A-Za-z0-9_-]{43}$/,
  );
  await page.getByRole("button", { name: "Done" }).click();

  const row = page.getByRole("row").filter({ hasText: name });
  await expect(row).toContainText("Active");

  return row;
};

const revoke = async (page: Page, name: string) => {
  await page
    .getByRole("row")
    .filter({ hasText: name })
    .getByRole("button", { name: `Actions for ${name}` })
    .click();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("menuitem", { name: "Revoke" }).click();
};

test("API-key page creates a secret and revokes the key", async ({ page }) => {
  await page.goto("/api-keys");
  await expect(page).toHaveURL(/\/api-keys$/);

  const workspaceMenu = page.getByRole("button", { name: "Workspace menu" });
  await expect(workspaceMenu).toContainText("Default");
  await workspaceMenu.click();
  await expect(page.getByRole("menuitem", { name: /Default/ })).toBeVisible();
  await page.keyboard.press("Escape");

  const keyName = `Playwright ${Date.now()}`;
  const row = await createKey(page, keyName);
  await revoke(page, keyName);
  await expect(row).toHaveCount(0);

  await page.getByRole("combobox", { name: "Key status" }).click();
  await page.getByRole("option", { name: "Revoked" }).click();
  await expect(
    page.getByRole("row").filter({ hasText: keyName }),
  ).toContainText("Revoked");
});

test("a failed revoke shows the problem and keeps the key active", async ({
  page,
}) => {
  await page.goto("/api-keys");

  const keyName = `Playwright ${Date.now()}`;
  const row = await createKey(page, keyName);

  await page.route(
    "**/api/v1/organizations/*/workspaces/*/api-keys/*",
    (route) =>
      route.request().method() === "DELETE"
        ? fulfillProblem(route, 500, "The key store is unavailable.")
        : route.fallback(),
  );
  await revoke(page, keyName);

  await expect(page.getByRole("alert")).toContainText(
    "The key store is unavailable.",
  );
  await expect(row).toContainText("Active");
});

test("an expired key is listed under Expired, not Active", async ({ page }) => {
  await page.route(apiPathEndsWith("/api-keys"), (route) =>
    fulfillJson(route, {
      data: [
        {
          id: "0198ae50-94d8-7d4d-a8be-0000000000e1",
          organization_id: "0198ae50-94d8-7d4d-a8be-0000000000bb",
          workspace_id: "0198ae50-94d8-7d4d-a8be-0000000000cc",
          name: "Expired key",
          expires_at: "2026-01-01T23:59:59.999Z",
          revoked_at: null,
          created_by: null,
          created_at: "2025-12-01T00:00:00.000Z",
          updated_at: "2025-12-01T00:00:00.000Z",
        },
      ],
      next_cursor: null,
    }),
  );
  await page.goto("/api-keys");

  await expect(page.getByText("No active API keys")).toBeVisible();

  await page.getByRole("combobox", { name: "Key status" }).click();
  await page.getByRole("option", { name: "Expired" }).click();

  const row = page.getByRole("row").filter({ hasText: "Expired key" });
  await expect(row).toContainText("Expired");
  await row.getByRole("button", { name: "Actions for Expired key" }).click();
  await expect(page.getByRole("menuitem", { name: "Revoke" })).toBeVisible();
});
