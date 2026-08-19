import { expect, test } from "./fixtures";

test("API-key page creates a secret and revokes the key", async ({ page }) => {
  await page.goto("/api-keys");
  await expect(page).toHaveURL(/\/api-keys$/);

  const workspaceMenu = page.getByRole("button", { name: "Workspace menu" });
  await expect(workspaceMenu).toContainText("Default");
  await workspaceMenu.click();
  await expect(page.getByRole("menuitem", { name: /Default/ })).toBeVisible();
  await page.keyboard.press("Escape");

  const keyName = `Playwright ${Date.now()}`;
  await page.getByRole("button", { name: "Create API key" }).click();
  await page.getByLabel("Name").fill(keyName);
  await page.getByRole("button", { name: "Create key" }).click();

  await expect(
    page.getByRole("heading", { name: "Copy your API key" }),
  ).toBeVisible();
  await expect(page.getByTestId("api-key-secret")).toHaveText(
    /^grad_[A-Za-z0-9_-]{43}$/,
  );
  await page.getByRole("button", { name: "Done" }).click();

  const row = page.getByRole("row").filter({ hasText: keyName });
  await expect(row).toContainText("Active");
  await row.getByRole("button", { name: `Actions for ${keyName}` }).click();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("menuitem", { name: "Revoke" }).click();
  await expect(row).toContainText("Revoked");
});
