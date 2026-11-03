import { expect, test, type Page } from "@playwright/test";

const setup = async (
  page: Page,
  {
    email,
    companyEmailDomain,
    onboardingCompleted = false,
    autoJoinDomain = null,
  }: {
    email: string;
    companyEmailDomain: string | null;
    onboardingCompleted?: boolean;
    autoJoinDomain?: string | null;
  },
) => {
  const organization = {
    id: "00000000-0000-4000-8000-000000000001",
    name: "Personal",
    role: "admin",
    status: "active",
    default_workspace_id: "00000000-0000-4000-8000-000000000002",
    auto_join_domain: autoJoinDomain,
    onboarding_completed: onboardingCompleted,
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
  const patches: unknown[] = [];

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
          email,
          email_verified: true,
          impersonation_expires_at: null as string | null,
          impersonated_by: null,
          is_staff: false,
          company_email_domain: companyEmailDomain,
          image_url: null,
          created_at: "2026-10-02T12:00:00Z",
          organizations: [organization],
        },
      });
    if (
      url.pathname === `/api/v1/organizations/${organization.id}` &&
      route.request().method() === "PATCH"
    ) {
      const patch = route.request().postDataJSON();
      patches.push(patch);
      Object.assign(organization, patch);
      return route.fulfill({ json: organization });
    }
    if (url.pathname.endsWith("/workspaces"))
      return route.fulfill({ json: { data: [workspace], next_cursor: null } });
    if (url.pathname.endsWith("/billing"))
      return route.fulfill({
        json: {
          organization_id: organization.id,
          mode: "prepaid",
          balance: "5000000000",
          created_at: workspace.created_at,
          updated_at: workspace.updated_at,
        },
      });
    if (url.pathname.startsWith("/api/"))
      return route.fulfill({ json: { data: [], next_cursor: null } });
    return route.continue();
  });

  return { patches };
};

test("a company-email owner names the organization and turns on domain joining", async ({
  page,
}) => {
  const { patches } = await setup(page, {
    email: "alex@acme.com",
    companyEmailDomain: "acme.com",
  });

  await page.goto("/api-keys");
  await expect(page).toHaveURL(/\/onboarding$/);
  const name = page.getByRole("textbox", { name: "Organization name" });
  await expect(name).toHaveValue("Acme");
  await expect(
    page.getByRole("checkbox", {
      name: "Let anyone with an @acme.com email join",
    }),
  ).toBeChecked();

  await name.fill("  Acme Corp ");
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(page).toHaveURL(/\/models\?welcome=true$/);
  expect(patches).toEqual([
    {
      name: "Acme Corp",
      auto_join_domain: "acme.com",
      onboarding_completed: true,
    },
  ]);
  await expect(page.getByText("Acme Corp is ready")).toBeVisible();
  await expect(
    page.getByText(
      "You have $5.00 in free credit. Set up your application with one of our models.",
    ),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Read the docs" }),
  ).toHaveAttribute("href", "https://gradiated.com/docs");
  await page.getByRole("button", { name: "Dismiss" }).click();
  await expect(page).toHaveURL(/\/models$/);
  await expect(page.getByText("Acme Corp is ready")).toHaveCount(0);
});

test("a company-email owner can leave domain joining off", async ({ page }) => {
  const { patches } = await setup(page, {
    email: "alex@acme.com",
    companyEmailDomain: "acme.com",
  });

  await page.goto("/onboarding");
  await page
    .getByRole("checkbox", { name: "Let anyone with an @acme.com email join" })
    .click();
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(page).toHaveURL(/\/models\?welcome=true$/);
  expect(patches).toEqual([
    { name: "Acme", auto_join_domain: null, onboarding_completed: true },
  ]);
});

test("a personal-email owner only names the organization", async ({ page }) => {
  const { patches } = await setup(page, {
    email: "alex@gmail.com",
    companyEmailDomain: null,
  });

  await page.goto("/onboarding");
  await expect(page.getByRole("checkbox")).toHaveCount(0);
  const continueButton = page.getByRole("button", { name: "Continue" });
  await expect(continueButton).toBeDisabled();

  await page
    .getByRole("textbox", { name: "Organization name" })
    .fill("Side project");
  await continueButton.click();

  await expect(page).toHaveURL(/\/models\?welcome=true$/);
  expect(patches).toEqual([
    { name: "Side project", onboarding_completed: true },
  ]);
});

test("onboarded admins skip setup and can turn domain joining off in settings", async ({
  page,
}) => {
  const { patches } = await setup(page, {
    email: "alex@acme.com",
    companyEmailDomain: "acme.com",
    onboardingCompleted: true,
    autoJoinDomain: "acme.com",
  });

  await page.goto("/onboarding");
  await expect(page).toHaveURL(/\/models$/);

  await page.goto("/settings/organization");
  const toggle = page.getByRole("switch", {
    name: "Anyone with an @acme.com email can join",
  });
  await expect(toggle).toBeChecked();
  await toggle.click();

  await expect(toggle).not.toBeChecked();
  expect(patches).toEqual([{ auto_join_domain: null }]);
  await toggle.click();
  await expect(toggle).toBeChecked();
  expect(patches).toEqual([
    { auto_join_domain: null },
    { auto_join_domain: "acme.com" },
  ]);
});
