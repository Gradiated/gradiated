import { expect, test, type Page } from "@playwright/test";

const organizationId = "00000000-0000-4000-8000-000000000001";
const workspaceId = "00000000-0000-4000-8000-000000000002";
const token = "a".repeat(43);

const setup = async (
  page: Page,
  {
    role = "admin",
    email = "alex@acme.com",
    signedIn = true,
    preview = "pending",
  }: {
    role?: "admin" | "member";
    email?: string;
    signedIn?: boolean;
    preview?: "pending" | "expired" | "invalid";
  } = {},
) => {
  const organization = {
    id: organizationId,
    name: "Acme",
    role,
    status: "active",
    default_workspace_id: workspaceId,
    auto_join_domain: null,
    onboarding_completed: true,
  };
  const me = {
    id: "user-alex",
    name: "Alex",
    email,
    email_verified: true,
    company_email_domain: "acme.com",
    image_url: null,
    created_at: "2026-09-01T12:00:00Z",
    organizations: email === "alex@acme.com" ? [organization] : [],
  };
  const members = [
    ["user-alex", "alex@acme.com", "admin"],
    ["user-sam", "sam@acme.com", "admin"],
    ["user-jordan", "jordan@acme.com", "member"],
  ].map(([user_id, memberEmail, memberRole]) => ({
    user_id,
    email: memberEmail,
    role: memberRole,
    joined_at: "2026-09-01T12:00:00Z",
  }));
  const invitations: Record<string, unknown>[] = [];
  const requests: { method: string; path: string; body: unknown }[] = [];

  await page.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.hostname !== "127.0.0.1") return route.abort();
    if (url.pathname.startsWith("/flags") || url.pathname.startsWith("/decide"))
      return route.fulfill({ json: { featureFlags: {}, flags: {} } });
    if (!url.pathname.startsWith("/api/")) return route.continue();

    const body = request.postData() ? request.postDataJSON() : undefined;
    requests.push({ method: request.method(), path: url.pathname, body });
    const base = `/api/v1/organizations/${organizationId}`;

    if (url.pathname === "/api/auth/get-session")
      return route.fulfill({
        json: signedIn ? { session: { id: "s" }, user: { email } } : null,
      });
    if (url.pathname === "/api/v1/me")
      return signedIn
        ? route.fulfill({ json: me })
        : route.fulfill({ status: 401, json: { status: 401 } });
    if (url.pathname.endsWith("/workspaces"))
      return route.fulfill({
        json: {
          data: [
            {
              id: workspaceId,
              organization_id: organizationId,
              name: "Production",
              is_default: true,
              trace_capture_enabled: true,
              trace_retention_days: 90,
              default_judge_model: "Qwen/Qwen3-0.6B",
              archived_at: null,
              created_at: "2026-09-01T12:00:00Z",
              updated_at: "2026-09-01T12:00:00Z",
            },
          ],
          next_cursor: null,
        },
      });
    if (url.pathname === `${base}/members`)
      return route.fulfill({ json: { data: members, next_cursor: null } });
    if (url.pathname.startsWith(`${base}/members/`)) {
      const userId = url.pathname.split("/").at(-1);
      const index = members.findIndex((member) => member.user_id === userId);
      if (request.method() === "DELETE") {
        members.splice(index, 1);
        return route.fulfill({ status: 204 });
      }
      members[index] = { ...members[index]!, ...body };
      return route.fulfill({ json: members[index] });
    }
    if (url.pathname === `${base}/invitations` && request.method() === "POST") {
      for (const invitedEmail of body.emails)
        invitations.push({
          id: `00000000-0000-4000-8000-00000000010${invitations.length}`,
          email: invitedEmail,
          role: body.role,
          invited_by_email: email,
          expires_at: new Date(Date.now() + 7 * 86_400_000).toISOString(),
          created_at: new Date().toISOString(),
        });
      return route.fulfill({
        status: 201,
        json: { data: invitations, next_cursor: null },
      });
    }
    if (url.pathname === `${base}/invitations`)
      return route.fulfill({ json: { data: invitations, next_cursor: null } });
    if (url.pathname.endsWith("/resend"))
      return route.fulfill({ json: invitations[0] });
    if (url.pathname.startsWith(`${base}/invitations/`)) {
      invitations.splice(0, 1);
      return route.fulfill({ status: 204 });
    }
    if (url.pathname === "/api/v1/invitations/preview")
      return route.fulfill({
        json:
          preview === "invalid"
            ? { status: "invalid" }
            : {
                status: preview,
                organization_id: organizationId,
                organization_name: "Acme",
                email: "morgan@acme.com",
                role: "member",
                invited_by_email: "sam@acme.com",
              },
      });
    if (url.pathname === "/api/v1/invitations/accept")
      return route.fulfill({ json: { ...organization, role: "member" } });

    return route.fulfill({ json: { data: [], next_cursor: null } });
  });
  page.on("dialog", (dialog) => void dialog.accept());

  return { requests, invitations };
};

test("admins invite, change roles and remove members", async ({ page }) => {
  const { requests } = await setup(page);

  await page.goto("/settings/members");
  await expect(page.getByText("alex@acme.com")).toBeVisible();
  await expect(
    page.getByRole("combobox", { name: "Role for alex@acme.com" }),
  ).toHaveCount(0);

  await page.getByRole("combobox", { name: "Role for sam@acme.com" }).click();
  await page.getByRole("option", { name: "Member" }).click();
  await expect
    .poll(() => requests.find((request) => request.method === "PATCH")?.body)
    .toEqual({ role: "member" });

  await page
    .getByRole("button", { name: "Actions for jordan@acme.com" })
    .click();
  await page.getByRole("menuitem", { name: "Remove from Acme" }).click();
  await expect(page.getByText("jordan@acme.com")).toHaveCount(0);

  await page.getByRole("button", { name: "Invite members" }).click();
  await page
    .getByRole("textbox", { name: "Email addresses" })
    .fill("Morgan@acme.com casey@acme.com, not-an-email");
  await expect(page.getByText("Check not-an-email.")).toBeVisible();
  await page
    .getByRole("textbox", { name: "Email addresses" })
    .fill("Morgan@acme.com casey@acme.com");
  await page.getByRole("button", { name: "Send 2 invitations" }).click();

  await expect(page.getByText("2 invitations sent.")).toBeVisible();
  expect(
    requests.find(
      (request) =>
        request.method === "POST" && request.path.endsWith("/invitations"),
    )?.body,
  ).toEqual({ emails: ["morgan@acme.com", "casey@acme.com"], role: "admin" });
  await expect(page.getByText("morgan@acme.com")).toBeVisible();

  await page
    .getByRole("button", {
      name: "Actions for the invitation to morgan@acme.com",
    })
    .click();
  await page.getByRole("menuitem", { name: "Revoke" }).click();
  await expect(page.getByText("morgan@acme.com")).toHaveCount(0);
});

test("members see a read-only list", async ({ page }) => {
  await setup(page, { role: "member" });

  await page.goto("/settings/members");

  await expect(page.getByText("sam@acme.com")).toBeVisible();
  await expect(page.getByRole("button", { name: /Invite/ })).toHaveCount(0);
  await expect(page.getByRole("combobox")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /^Actions for/ })).toHaveCount(
    0,
  );
});

test("settings groups stay labelled on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await setup(page);

  await page.goto("/settings");
  await expect(page).toHaveURL(/\/settings\/workspace$/);

  const organization = page.getByRole("group", { name: "Organization" });
  await expect(organization.getByText("Organization")).toBeVisible();
  await organization.getByRole("link", { name: "Members" }).click();
  await expect(page).toHaveURL(/\/settings\/members$/);
  await expect(page.getByRole("button", { name: "Invite" })).toBeVisible();
});

test("an invited user joins and lands on Models", async ({ page }) => {
  const { requests } = await setup(page, { email: "morgan@acme.com" });

  await page.goto(`/invitations/accept?token=${token}`);
  await page.getByRole("button", { name: "Join Acme" }).click();

  await expect(page).toHaveURL(/\/models$/);
  expect(
    requests.find((request) => request.path === "/api/v1/invitations/accept")
      ?.body,
  ).toEqual({ token });
});

test("a signed-out invitee is sent to sign in with the invitation filled in", async ({
  page,
}) => {
  await setup(page, { signedIn: false });

  await page.goto(`/invitations/accept?token=${token}`);

  await expect(
    page.getByRole("heading", { name: "Sign in to join Acme" }),
  ).toBeVisible();
  await expect(page.getByLabel("Email")).toHaveValue("morgan@acme.com");
  await expect(page).toHaveURL(new RegExp(`invitation=${token}`));
});

test("expired and invalid links explain what to do", async ({ page }) => {
  await setup(page, { preview: "expired" });
  await page.goto(`/invitations/accept?token=${token}`);
  await expect(
    page.getByRole("heading", { name: "This invitation has expired" }),
  ).toBeVisible();

  await page.goto("/invitations/accept?token=nope");
  await expect(
    page.getByRole("heading", { name: "This invitation link isn't valid" }),
  ).toBeVisible();
});
