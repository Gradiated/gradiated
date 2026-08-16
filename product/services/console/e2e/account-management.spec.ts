import { expect, test } from "@playwright/test";

test("account menus create and select organizations and workspaces", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(page).toHaveURL(/\/api-keys$/);

  const accountMenu = page.getByRole("button", { name: "Account menu" });
  await accountMenu.click();
  await page.getByRole("menuitem", { name: "Change organization" }).hover();
  await expect(
    page.getByRole("menuitem", { name: /Local Development/ }),
  ).toBeVisible();

  const organizationName = `Playwright Org ${Date.now()}`;
  await page.getByRole("menuitem", { name: "Add organization" }).click();
  await expect(
    page.getByRole("heading", { name: "Create an organization" }),
  ).toBeVisible();
  await page.getByLabel("Organization name").fill(organizationName);
  await page.getByRole("button", { name: "Create organization" }).click();

  const workspaceMenu = page.getByRole("button", { name: "Workspace menu" });
  await expect(workspaceMenu).toContainText("Default");
  await accountMenu.click();
  await page.getByRole("menuitem", { name: "Change organization" }).hover();
  await expect(
    page.getByRole("menuitem", { name: organizationName }),
  ).toBeVisible();
  await page.keyboard.press("Escape");

  const workspaceName = `Playwright Workspace ${Date.now()}`;
  await workspaceMenu.click();
  await page.getByRole("menuitem", { name: "Add workspace" }).click();
  await expect(
    page.getByRole("heading", { name: "Create a workspace" }),
  ).toBeVisible();
  await page.getByLabel("Workspace name").fill(workspaceName);
  await page.getByRole("button", { name: "Create workspace" }).click();
  await expect(workspaceMenu).toContainText(workspaceName);

  await workspaceMenu.click();
  await expect(
    page.getByRole("menuitem", { name: workspaceName }),
  ).toBeVisible();
});
