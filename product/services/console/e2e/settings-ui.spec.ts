import { expect, test, type Page } from "@playwright/test";

const setup = async (page: Page, role = "admin") => {
  const organization = {
    id: "00000000-0000-4000-8000-000000000001",
    name: "Example organization",
    role,
    status: "active",
    default_workspace_id: "00000000-0000-4000-8000-000000000002",
    slug: "example",
    auto_join_domain: null,
    onboarding_completed: true,
  };
  const workspace = {
    id: organization.default_workspace_id,
    organization_id: organization.id,
    name: "Default",
    is_default: true,
    trace_capture_enabled: true,
    trace_retention_days: 90,
    default_judge_model: "Qwen/Qwen3-0.6B",
    archived_at: null,
    created_at: "2026-10-02T12:00:00Z",
    updated_at: "2026-10-02T12:00:00Z",
  };
  let rejectOrganization = true;
  await page.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.hostname !== "127.0.0.1") return route.abort();
    if (url.pathname.startsWith("/flags") || url.pathname.startsWith("/decide"))
      return route.fulfill({ json: { featureFlags: {}, flags: {} } });
    if (url.pathname === "/api/v1/me")
      return route.fulfill({
        json: {
          id: "test-user",
          name: "Test User",
          email: "test@example.invalid",
          organizations: [organization],
        },
      });
    if (url.pathname.endsWith("/workspaces"))
      return route.fulfill({ json: { data: [workspace], next_cursor: null } });
    if (route.request().method() === "PATCH") {
      const { name, slug } = route.request().postDataJSON();
      if (url.pathname === `/api/v1/workspaces/${workspace.id}`) {
        workspace.name = name;
        return route.fulfill({ json: workspace });
      }
      if (url.pathname === `/api/v1/organizations/${organization.id}`) {
        if (slug === "taken")
          return route.fulfill({
            status: 409,
            json: { detail: "Another organization already uses this slug." },
          });
        if (slug !== undefined) {
          organization.slug = slug;
          return route.fulfill({ json: organization });
        }
        if (rejectOrganization) {
          rejectOrganization = false;
          return route.fulfill({ status: 503, json: { detail: "Try again" } });
        }
        organization.name = name;
        return route.fulfill({ json: organization });
      }
    }
    if (url.pathname.startsWith("/api/"))
      return route.fulfill({ json: { data: [], next_cursor: null } });
    return route.continue();
  });
  return { organization, workspace };
};

test("settings rename the selected scopes, persist on reload, and preserve input after a failed save", async ({
  page,
}) => {
  const { organization, workspace } = await setup(page);
  await page.goto("/settings");
  await expect(page).toHaveURL(/\/settings\/workspace$/);
  const input = page.getByRole("textbox", { name: "Workspace name" });
  await expect(input).toHaveAttribute("data-1p-ignore", "true");
  await expect(input).toHaveAttribute("autocomplete", "off");
  await input.fill("  Production  ");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect.poll(() => workspace.name).toBe("Production");
  await expect(
    page.getByRole("button", { name: "Workspace menu" }),
  ).toContainText("Production");
  await page.reload();
  await expect(input).toHaveValue("Production");
  await page
    .getByRole("group", { name: "Organization" })
    .getByRole("link", { name: "General" })
    .click();
  const organizationInput = page.getByRole("textbox", {
    name: "Organization name",
  });
  const saveName = page
    .locator("form")
    .filter({ has: organizationInput })
    .getByRole("button", { name: "Save changes" });
  await organizationInput.fill("Research");
  await saveName.click();
  // Save errors are toasts.
  await expect(page.getByText(/Try again/)).toBeVisible();
  await expect(organizationInput).toHaveValue("Research");
  expect(organization.name).toBe("Example organization");
  await saveName.click();
  await expect.poll(() => organization.name).toBe("Research");
  await page.reload();
  await page
    .getByRole("group", { name: "Organization" })
    .getByRole("link", { name: "General" })
    .click();
  await expect(organizationInput).toHaveValue("Research");
});

test("ordinary members can view names but cannot edit them", async ({
  page,
}) => {
  await setup(page, "member");
  await page.goto("/settings");
  await expect(
    page.getByRole("textbox", { name: "Workspace name" }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Save changes" }),
  ).toBeDisabled();
  await page
    .getByRole("group", { name: "Organization" })
    .getByRole("link", { name: "General" })
    .click();
  await expect(
    page.getByRole("textbox", { name: "Organization name" }),
  ).toBeDisabled();
  await expect(
    page.getByRole("textbox", { name: "Organization slug" }),
  ).toBeDisabled();
});

test("admins change the organization slug and see conflicts in the form", async ({
  page,
}) => {
  const { organization } = await setup(page);
  await page.goto("/settings/organization");
  const slugInput = page.getByRole("textbox", { name: "Organization slug" });
  const saveSlug = page.getByRole("button", { name: "Save slug" });
  await expect(slugInput).toHaveValue("example");
  await expect(page.getByText("example/support-triage")).toBeVisible();

  await slugInput.fill("-bad");
  await expect(page.getByRole("alert")).toContainText(
    "Use 2 to 39 lowercase letters",
  );
  await expect(saveSlug).toBeDisabled();

  await slugInput.fill("taken");
  await saveSlug.click();
  await expect(page.getByRole("alert")).toContainText(
    "Another organization already uses this slug.",
  );
  expect(organization.slug).toBe("example");

  await slugInput.fill("Research-Lab");
  await expect(page.getByText("research-lab/support-triage")).toBeVisible();
  await saveSlug.click();
  await expect.poll(() => organization.slug).toBe("research-lab");
  await page.reload();
  await expect(slugInput).toHaveValue("research-lab");
});
