import { expect, test, type Page, type Route } from "@playwright/test";

const setup = async (
  page: Page,
  {
    email,
    companyEmailDomain,
    onboardingCompleted = false,
    autoJoinDomain = null,
    signedIn = true,
    engineer = engineerProviders(),
  }: {
    email: string;
    companyEmailDomain: string | null;
    onboardingCompleted?: boolean;
    autoJoinDomain?: string | null;
    signedIn?: boolean;
    engineer?: EngineerProviders;
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
    if (url.pathname === "/api/v1/me" && !signedIn)
      return route.fulfill({
        status: 401,
        json: { title: "Unauthorized", status: 401, detail: "Sign in." },
      });
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
    if (
      url.pathname.startsWith(`/api/v1/organizations/${organization.id}/`) &&
      (await engineerRoute(route, url, engineer))
    )
      return;
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

  return { patches, engineer };
};

type EngineerOnboarding = {
  nda: { document_id: string; signed_at: string } | null;
  slack: {
    channel_id: string;
    channel_name: string;
    status: "pending" | "active";
    invited_email: string | null;
    invited_at: string | null;
  } | null;
  github_installations: unknown[];
  contact_channel: "slack" | "email" | null;
  submitted_at: string | null;
};

const engineerProviders = (onboarding: Partial<EngineerOnboarding> = {}) => ({
  onboarding: {
    nda: null,
    slack: null,
    github_installations: [],
    contact_channel: null,
    submitted_at: null,
    ...onboarding,
  } as EngineerOnboarding,
  ndaSigned: false,
  githubInstalled: true,
  ndaDocuments: [] as unknown[],
  signingSessions: 0,
  slackInvitations: [] as unknown[],
  submissions: [] as unknown[],
});

type EngineerProviders = ReturnType<typeof engineerProviders>;

const signedAt = "2026-11-09T12:00:00.000Z";

/* PandaDoc, Slack and GitHub are stubbed at the API boundary, so a run never
   creates a real NDA, Slack channel or GitHub check. */
const engineerRoute = async (
  route: Route,
  url: URL,
  engineer: EngineerProviders,
) => {
  const method = route.request().method();
  const path = url.pathname.split("/").slice(5).join("/");
  const ndaDocument = (details: unknown) => ({
    id: "nda-document-1",
    status: engineer.ndaSigned ? "completed" : "ready",
    details,
    completed_at: engineer.ndaSigned ? signedAt : null,
    customer_completed: engineer.ndaSigned,
  });

  if (path === "engineer-onboarding" && method === "GET") {
    await route.fulfill({ json: engineer.onboarding });
    return true;
  }
  if (path === "nda-documents" && method === "POST") {
    engineer.ndaDocuments.push(route.request().postDataJSON());
    await route.fulfill({
      status: 201,
      json: ndaDocument(engineer.ndaDocuments.at(-1)),
    });
    return true;
  }
  if (path === "nda-documents/nda-document-1" && method === "GET") {
    if (engineer.ndaSigned)
      engineer.onboarding.nda = {
        document_id: "nda-document-1",
        signed_at: signedAt,
      };
    await route.fulfill({ json: ndaDocument(engineer.ndaDocuments.at(-1)) });
    return true;
  }
  if (path === "nda-documents/nda-document-1/signing-sessions") {
    engineer.signingSessions += 1;
    await route.fulfill({ status: 201, json: { session_id: "session-1" } });
    return true;
  }
  if (path === "github-installations") {
    await route.fulfill({
      json: engineer.githubInstalled
        ? {
            status: "installed",
            installations: [
              {
                id: 42,
                account: "acme",
                repository_selection: "selected",
                repository_count: 3,
              },
            ],
          }
        : { status: "not_installed", installations: [] },
    });
    return true;
  }
  if (path === "slack-invitations" && method === "POST") {
    const invitation = route.request().postDataJSON() as { email: string };
    engineer.slackInvitations.push(invitation);
    engineer.onboarding.slack = {
      channel_id: "C123",
      channel_name: "ext-acme-gradiated",
      status: "active",
      invited_email: invitation.email,
      invited_at: signedAt,
    };
    await route.fulfill({
      status: 201,
      json: {
        channel_id: "C123",
        channel_name: "ext-acme-gradiated",
        email: invitation.email,
        status: "invited",
      },
    });
    return true;
  }
  if (path === "engineer-onboarding/submission" && method === "POST") {
    const submission = route.request().postDataJSON() as {
      contact_channel: "slack" | "email";
    };
    engineer.submissions.push(submission);
    engineer.onboarding.contact_channel = submission.contact_channel;
    engineer.onboarding.submitted_at = signedAt;
    await route.fulfill({ status: 201, json: engineer.onboarding });
    return true;
  }

  return false;
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

test("a new engineer customer sets up the organization, signs the NDA, invites Slack and starts a project", async ({
  page,
}) => {
  const { patches, engineer } = await setup(page, {
    email: "alex@acme.com",
    companyEmailDomain: "acme.com",
  });

  await page.goto("/onboarding/post-training");
  await expect(page).toHaveURL(/\/onboarding\?journey=post-training$/);
  await page.getByRole("button", { name: "Continue" }).click();

  expect(patches).toEqual([
    { name: "Acme", auto_join_domain: "acme.com", onboarding_completed: true },
  ]);
  await page.getByRole("button", { name: "Get started" }).click();

  await expect(
    page.getByRole("textbox", { name: "Legal company name" }),
  ).toHaveValue("Acme");
  await page
    .getByRole("textbox", { name: "Legal company name" })
    .fill("Acme, Inc.");
  await page.getByRole("textbox", { name: "Signer’s title" }).fill("CTO");
  await page
    .getByRole("textbox", { name: "Company address" })
    .fill("1 Market Street, San Francisco, CA 94105, USA");
  await page.getByRole("button", { name: "Review & sign NDA" }).click();

  await expect(
    page.getByRole("heading", { name: "Review & sign your NDA" }),
  ).toBeVisible();
  await expect.poll(() => engineer.signingSessions).toBe(1);
  expect(engineer.ndaDocuments).toEqual([
    {
      company: "Acme, Inc.",
      name: "Test User",
      title: "CTO",
      address: "1 Market Street, San Francisco, CA 94105, USA",
      email: "alex@acme.com",
    },
  ]);

  engineer.ndaSigned = true;
  await page.getByRole("button", { name: "Check signing status" }).click();

  await expect(
    page.getByRole("heading", { name: "Set up Slack & GitHub" }),
  ).toBeVisible();
  await expect(
    page.getByText("Installed · acme · 3 repositories"),
  ).toBeVisible();
  await expect(
    page.getByText(
      "We’ll create #ext-acme-gradiated and invite alex@acme.com.",
    ),
  ).toBeVisible();
  await page.getByRole("button", { name: "Send Slack invite" }).click();

  await expect(
    page.getByText("Invite sent · #ext-acme-gradiated"),
  ).toBeVisible();
  expect(engineer.slackInvitations).toEqual([{ email: "alex@acme.com" }]);
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(
    page.getByRole("heading", { name: "Let’s get to work" }),
  ).toBeVisible();
  await expect(
    page.getByText("#ext-acme-gradiated · invitation sent"),
  ).toBeVisible();
  await page
    .getByRole("textbox", { name: /Anything else you’d like us to know/ })
    .fill("  Our support agent calls the wrong tool.  ");
  await page.getByRole("button", { name: "Start project" }).click();

  await expect(
    page.getByRole("heading", { name: "You’re all set" }),
  ).toBeVisible();
  await expect(page.getByText(/will suggest a plan on Slack/)).toBeVisible();
  expect(engineer.submissions).toEqual([
    {
      contact_channel: "slack",
      github_installation_id: 42,
      notes: "Our support agent calls the wrong tool.",
    },
  ]);
});

test("a returning customer with a signed NDA waits for GitHub, chooses email and resumes at the confirmation", async ({
  page,
}) => {
  const { engineer } = await setup(page, {
    email: "alex@acme.com",
    companyEmailDomain: "acme.com",
    onboardingCompleted: true,
    engineer: engineerProviders({
      nda: { document_id: "nda-document-1", signed_at: signedAt },
    }),
  });
  engineer.githubInstalled = false;

  await page.goto("/onboarding?journey=post-training");
  await expect(
    page.getByRole("heading", { name: "Set up Slack & GitHub" }),
  ).toBeVisible();
  await page
    .getByRole("checkbox", {
      name: "Our team can’t use Slack — use email instead.",
    })
    .click();
  await expect(
    page.getByRole("button", { name: "Send Slack invite" }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Continue" }).click();
  await expect(
    page.getByText(/Install the Gradiated GitHub app and select at least one/),
  ).toBeVisible();

  engineer.githubInstalled = true;
  await page.getByRole("button", { name: "Check installation" }).click();
  await expect(
    page.getByText("Installed · acme · 3 repositories"),
  ).toBeVisible();
  await page.getByRole("button", { name: "Continue" }).click();

  await expect(
    page.getByText("Email fallback · Slack unavailable"),
  ).toBeVisible();
  await page.getByRole("button", { name: "Start project" }).click();

  await expect(
    page.getByText(/will email a plan to alex@acme.com/),
  ).toBeVisible();
  expect(engineer.submissions).toEqual([
    { contact_channel: "email", github_installation_id: 42 },
  ]);
  expect(engineer.slackInvitations).toEqual([]);
  expect(engineer.ndaDocuments).toEqual([]);

  await page.reload();
  await expect(
    page.getByRole("heading", { name: "You’re all set" }),
  ).toBeVisible();
});

test("a signed-out visitor is sent to sign in and kept on the post-training journey", async ({
  page,
}) => {
  await setup(page, {
    email: "alex@acme.com",
    companyEmailDomain: "acme.com",
    signedIn: false,
  });

  await page.goto("/onboarding/post-training");

  await expect(page).toHaveURL(/\/login\?journey=post-training$/);
});

test("onboarded admins without the journey still skip onboarding", async ({
  page,
}) => {
  await setup(page, {
    email: "alex@acme.com",
    companyEmailDomain: "acme.com",
    onboardingCompleted: true,
  });

  await page.goto("/onboarding/unknown");

  await expect(page).toHaveURL(/\/models$/);
});
