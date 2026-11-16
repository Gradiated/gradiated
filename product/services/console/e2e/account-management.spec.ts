import { expect, test } from "./fixtures";

test("account menus create and select organizations and workspaces", async ({
  account,
  page,
}) => {
  await page.goto("/api-keys");
  await expect(page).toHaveURL(/\/api-keys$/);

  const accountMenu = page.getByRole("button", { name: "Account menu" });
  await accountMenu.click();
  await page.getByRole("menuitem", { name: "Change organization" }).hover();
  await expect(
    page.getByRole("menuitem", { name: account.organizationName }),
  ).toBeVisible();

  const organizationName = `Playwright Org ${Date.now()}`;
  await page.getByRole("menuitem", { name: "Add organization" }).click();
  await expect(
    page.getByRole("heading", { name: "Create an organization" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Create organization" }).click();
  await expect(page.getByText("Enter an organization name.")).toBeVisible();
  await expect(page.getByLabel("Organization name")).toHaveAttribute(
    "data-1p-ignore",
    "true",
  );
  await expect(page.getByLabel("Organization name")).toHaveAttribute(
    "name",
    "scopeLabel",
  );
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
  await expect(page.getByLabel("Workspace name")).toHaveAttribute(
    "data-1p-ignore",
    "true",
  );
  await expect(page.getByLabel("Workspace name")).toHaveAttribute(
    "name",
    "scopeLabel",
  );
  await page.getByLabel("Workspace name").fill(workspaceName);

  const workspacesRoute = "**/api/v1/organizations/*/workspaces";
  await page.route(workspacesRoute, async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ detail: "boom" }),
    });
  });
  await page.getByRole("button", { name: "Create workspace" }).click();
  await expect(page.getByText("boom", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Create a workspace" }),
  ).toBeVisible();
  await page.unroute(workspacesRoute);

  await page.getByRole("button", { name: "Create workspace" }).click();
  await expect(workspaceMenu).toContainText(workspaceName);

  const secondWorkspaceName = `${workspaceName} B`;
  await workspaceMenu.click();
  await page.getByRole("menuitem", { name: "Add workspace" }).click();
  await expect(page.getByLabel("Workspace name")).toHaveValue("");
  await page.getByLabel("Workspace name").fill(secondWorkspaceName);
  await page.getByRole("button", { name: "Create workspace" }).click();
  await expect(workspaceMenu).toContainText(secondWorkspaceName);

  await workspaceMenu.click();
  await expect(
    page.getByRole("menuitem", { name: new RegExp(`${workspaceName}$`) }),
  ).toBeVisible();
  await expect(
    page.getByRole("menuitem", { name: secondWorkspaceName }),
  ).toBeVisible();
});

test("the console shell waits for the current user to load", async ({
  page,
}) => {
  await page.route("**/api/v1/me", () => undefined);
  await page.goto("/api-keys");

  await expect(page.getByLabel("Loading")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Workspace menu" }),
  ).toHaveCount(0);
});

test("settings save organization and workspace names across reloads", async ({
  account,
  page,
}) => {
  await page.goto("/api-keys");
  await page.getByRole("link", { name: "Settings", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Settings", exact: true }),
  ).toBeVisible();
  const workspaceName = `Production ${Date.now()}`;
  await page
    .getByRole("textbox", { name: "Workspace name" })
    .fill(workspaceName);
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(
    page.getByRole("button", { name: "Workspace menu" }),
  ).toContainText(workspaceName);
  await page.reload();
  await expect(
    page.getByRole("textbox", { name: "Workspace name" }),
  ).toHaveValue(workspaceName);
  await page
    .getByRole("group", { name: "Organization" })
    .getByRole("link", { name: "General" })
    .click();
  await expect(
    page.getByRole("textbox", { name: "Organization name" }),
  ).toHaveValue(account.organizationName);
  const organizationName = `Research ${Date.now()}`;
  await page
    .getByRole("textbox", { name: "Organization name" })
    .fill(organizationName);
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(
    page.getByText("Organization renamed.", { exact: true }),
  ).toBeVisible();
  await page.reload();
  await page
    .getByRole("group", { name: "Organization" })
    .getByRole("link", { name: "General" })
    .click();
  await expect(
    page.getByRole("textbox", { name: "Organization name" }),
  ).toHaveValue(organizationName);
});
