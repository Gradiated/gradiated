import { expect, test, type Page } from "@playwright/test";

const organizationId = "00000000-0000-4000-8000-000000000001";
const workspaceId = "00000000-0000-4000-8000-000000000002";
const token = "a".repeat(43);

const setup = async (
  page: Page,
  {
    role = "admin",
    isStaff = false,
    beforeMeRefresh,
    email = "alex@acme.com",
    signedIn = true,
    preview = "pending",
    now = Date.now,
  }: {
    role?: "admin" | "member";
    isStaff?: boolean;
    beforeMeRefresh?: () => Promise<void>;
    email?: string;
    signedIn?: boolean;
    preview?: "pending" | "expired" | "invalid";
    now?: () => number;
  } = {},
) => {
  const organization = {
    id: organizationId,
    name: "Acme",
    role,
    status: "active",
    default_workspace_id: workspaceId,
    slug: "acme",
    auto_join_domain: null,
    onboarding_completed: true,
  };
  const me = {
    id: "user-alex",
    name: "Alex",
    email,
    email_verified: true,
    impersonation_expires_at: null as string | null,
    impersonated_by: null as string | null,
    is_staff: isStaff,
    company_email_domain: "acme.com",
    image_url: null,
    created_at: "2026-09-01T12:00:00Z",
    organizations: email === "alex@acme.com" ? [organization] : [],
  };
  const staffProfile = { ...me };
  const allOrganizations = me.organizations;
  let sessionActive = signedIn;
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
  let meReads = 0;
  const requests: { method: string; path: string; body: unknown }[] = [];

  await page.context().route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.hostname !== "127.0.0.1") return route.abort();
    if (url.pathname.startsWith("/flags") || url.pathname.startsWith("/decide"))
      return route.fulfill({ json: { featureFlags: {}, flags: {} } });
    if (!url.pathname.startsWith("/api/")) return route.continue();

    const body = request.postData() ? request.postDataJSON() : undefined;
    requests.push({ method: request.method(), path: url.pathname, body });
    const base = `/api/v1/organizations/${organizationId}`;

    if (
      url.pathname === "/api/v1/admin/organizations" &&
      request.method() === "GET"
    ) {
      const search = url.searchParams.get("search") ?? "";
      const offset = Number(url.searchParams.get("offset") ?? 0);
      const limit = Number(url.searchParams.get("limit") ?? 20);
      const rows = allOrganizations.filter((item) =>
        item.name.toLowerCase().includes(search.toLowerCase()),
      );
      return route.fulfill({
        json: {
          data: rows.slice(offset, offset + limit),
          has_more: rows.length > offset + limit,
        },
      });
    }
    if (
      url.pathname.startsWith("/api/v1/admin/organizations/") &&
      request.method() === "GET"
    ) {
      const organization = allOrganizations.find(
        (item) => item.id === url.pathname.split("/").at(-1),
      );
      return organization
        ? route.fulfill({ json: organization })
        : route.fulfill({ status: 404, json: { status: 404 } });
    }
    if (url.pathname === "/api/auth/sign-out") {
      sessionActive = false;
      return route.fulfill({ json: { success: true } });
    }
    if (url.pathname === "/api/auth/get-session")
      return route.fulfill({
        json: sessionActive
          ? { session: { id: "s" }, user: { email: me.email } }
          : null,
      });
    if (
      url.pathname === "/api/v1/admin/organizations" &&
      request.method() === "POST"
    ) {
      const created = {
        ...organization,
        id: "00000000-0000-4000-8000-000000000003",
        name: body.name,
      };
      me.organizations.push(created);
      return route.fulfill({
        status: 201,
        json: {
          ...created,
          kind: "customer",
          created_at: me.created_at,
          updated_at: me.created_at,
        },
      });
    }
    if (url.pathname === "/api/v1/admin/impersonations") {
      const target = members.find((item) => item.user_id === body.user_id)!;
      Object.assign(me, {
        id: target.user_id,
        email: target.email,
        name: "Customer",
        is_staff: false,
        impersonated_by: staffProfile.id,
        impersonation_expires_at: new Date(
          now() + 15 * 60 * 1000,
        ).toISOString(),
      });
      return route.fulfill({ json: { user_id: target.user_id } });
    }
    if (url.pathname === "/api/v1/admin/impersonations/stop") {
      Object.assign(me, staffProfile);
      return route.fulfill({ json: { user_id: staffProfile.id } });
    }
    if (url.pathname === "/api/v1/me") {
      if (
        me.impersonated_by &&
        me.impersonation_expires_at &&
        Date.parse(me.impersonation_expires_at) <= now()
      )
        return route.fulfill({
          status: 401,
          json: { code: "staff_session_recovery_required" },
        });

      if (meReads++ > 0) await beforeMeRefresh?.();

      return sessionActive
        ? route.fulfill({ json: me })
        : route.fulfill({ status: 401, json: { status: 401 } });
    }
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

  return { requests, invitations, me };
};

test("admins invite, change roles and remove members", async ({ page }) => {
  const { requests } = await setup(page);

  await page.goto("/settings/members");
  await expect(
    page.getByRole("table").getByText("alex@acme.com", { exact: true }),
  ).toBeVisible();
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

test("staff can invite customers before signup from the organization page", async ({
  page,
}) => {
  const { requests } = await setup(page, { isStaff: true });
  await page.goto("/admin");
  await expect(
    page.getByRole("heading", { name: "Admin portal" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Invite people" })).toHaveCount(
    0,
  );
  await page
    .locator(`a[href="/admin/organizations/${organizationId}"]`)
    .click();
  await page.getByRole("button", { name: "Invite people" }).click();
  await page.getByLabel("Email addresses").fill("new-customer@acme.com");
  await page.getByRole("combobox").click();
  await page.getByRole("option", { name: "Admin", exact: true }).click();
  await page.getByRole("button", { name: "Send invitation" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(
    requests.find(
      (request) =>
        request.method === "POST" && request.path.endsWith("/invitations"),
    )?.body,
  ).toEqual({ emails: ["new-customer@acme.com"], role: "admin" });
  await expect(
    page.getByRole("link", { name: "Set up workspace" }),
  ).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Manage members" })).toHaveCount(
    0,
  );
});

test("organization admins without staff status cannot open the staff portal", async ({
  page,
}) => {
  await setup(page);
  await page.goto("/admin");
  await expect(page).toHaveURL(/\/api-keys$/);
  await expect(page.getByRole("link", { name: "Admin portal" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Admin portal" })).toHaveCount(
    0,
  );
});

test("staff keep the new organization selected during a slow account refresh", async ({
  page,
}) => {
  let releaseRefresh!: () => void;
  const refreshBlocked = new Promise<void>((resolve) => {
    releaseRefresh = resolve;
  });
  const { requests } = await setup(page, {
    isStaff: true,
    beforeMeRefresh: () => refreshBlocked,
  });
  await page.goto("/admin");
  await page.getByRole("button", { name: "Create organization" }).click();
  await page.getByLabel("Organization name").fill("Prepared Customer");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Create organization" })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(
    page.getByText("Prepared Customer", { exact: true }).first(),
  ).toBeVisible();
  expect(
    requests.filter(
      (request) =>
        request.path === "/api/v1/admin/organizations" &&
        request.method === "POST",
    ),
  ).toEqual([
    {
      method: "POST",
      path: "/api/v1/admin/organizations",
      body: { name: "Prepared Customer", slug: "prepared-customer" },
    },
  ]);
  const selectedOrganization = () =>
    page.evaluate(
      () =>
        JSON.parse(localStorage.getItem("gradiated-workspace-selection")!).state
          .organizationId,
    );
  await expect
    .poll(selectedOrganization)
    .toBe("00000000-0000-4000-8000-000000000003");
  const refreshed = page.waitForResponse(
    (response) => new URL(response.url()).pathname === "/api/v1/me",
  );
  releaseRefresh();
  await refreshed;
  await expect
    .poll(selectedOrganization)
    .toBe("00000000-0000-4000-8000-000000000003");
  await page.reload();
  await expect(
    page.getByText("Prepared Customer", { exact: true }).first(),
  ).toBeVisible();
  await expect
    .poll(selectedOrganization)
    .toBe("00000000-0000-4000-8000-000000000003");
});

test("staff view an organization's users, impersonate a customer and return to staff", async ({
  page,
}) => {
  const { requests } = await setup(page, { isStaff: true });
  await page.goto("/admin");
  await expect(
    page.getByRole("heading", { name: "All organizations" }),
  ).toBeVisible();
  await page
    .locator(`a[href="/admin/organizations/${organizationId}"]`)
    .click();
  await expect(page).toHaveURL(
    new RegExp(`/admin/organizations/${organizationId}$`),
  );
  await expect(
    page.getByRole("heading", { name: "Users", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Impersonate sam@acme.com" }).click();
  await expect(page).toHaveURL(/\/api-keys$/);
  await expect(
    page.getByRole("status").filter({ hasText: "Viewing as" }),
  ).toContainText("sam@acme.com");
  await expect(page.getByRole("link", { name: "Admin portal" })).toHaveCount(0);
  expect(
    requests.find((request) => request.path === "/api/v1/admin/impersonations")
      ?.body,
  ).toEqual({ user_id: "user-sam" });
  await page.getByRole("button", { name: "Return to staff account" }).click();
  await expect(page).toHaveURL(/\/admin$/);
  await expect(
    page.getByRole("heading", { name: "Admin portal", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Viewing as", { exact: false })).toHaveCount(0);
});

test("non-staff cannot open an organization's staff detail page", async ({
  page,
}) => {
  await setup(page);
  await page.goto(`/admin/organizations/${organizationId}`);
  await expect(page).toHaveURL(/\/api-keys$/);
  await expect(page.getByRole("button", { name: /Impersonate/ })).toHaveCount(
    0,
  );
});

test("staff search organizations on the server and use compact table navigation", async ({
  page,
}) => {
  const { requests } = await setup(page, { isStaff: true });
  await page.goto("/admin");
  await expect(page.getByRole("table")).toBeVisible();
  await expect(
    page.getByRole("link", { name: "View organization" }),
  ).toHaveCount(0);
  await page
    .getByRole("searchbox", { name: "Search organizations" })
    .fill("missing");
  await expect(
    page.getByText("No organizations match your search."),
  ).toBeVisible();
  expect(
    requests.some((request) => request.path === "/api/v1/admin/organizations"),
  ).toBe(true);
  await page.getByRole("searchbox").fill("aCmE");
  await page
    .locator(`a[href="/admin/organizations/${organizationId}"]`)
    .click();
  await page
    .getByRole("link", { name: "All organizations", exact: true })
    .click();
  await expect(page).toHaveURL(/\/admin$/);
});

test("staff paginate server results and reset the page when searching", async ({
  page,
}) => {
  await setup(page, { isStaff: true });
  const queries: { search: string; offset: number }[] = [];
  await page.route("**/api/v1/admin/organizations?**", async (route) => {
    const url = new URL(route.request().url());
    const search = url.searchParams.get("search") ?? "";
    const offset = Number(url.searchParams.get("offset"));
    queries.push({ search, offset });
    return route.fulfill({
      json: {
        data: [
          {
            id: organizationId,
            name: search || `Customer ${offset + 1}`,
            status: "active",
            role: "admin",
            default_workspace_id: workspaceId,
            auto_join_domain: null,
            onboarding_completed: true,
          },
        ],
        has_more: offset === 0 && !search,
      },
    });
  });
  await page.goto("/admin");
  await expect(
    page.getByRole("link", { name: "Customer 1", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(
    page.getByRole("link", { name: "Customer 21", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Next", exact: true }),
  ).toBeDisabled();
  await page.getByRole("searchbox").fill("Acme");
  await expect(
    page.getByRole("link", { name: "Acme", exact: true }),
  ).toBeVisible();
  expect(queries).toContainEqual({ search: "", offset: 20 });
  expect(queries.at(-1)).toEqual({ search: "Acme", offset: 0 });
  await expect(
    page.getByRole("button", { name: "Previous", exact: true }),
  ).toBeDisabled();
});

test("impersonation countdown survives reload and automatically returns to staff at 15 minutes", async ({
  page,
}) => {
  let elapsed = 0;
  const now = () => Date.now() + elapsed;
  await page.clock.install({ time: now() });
  const { requests } = await setup(page, { isStaff: true, now });
  await page.goto(`/admin/organizations/${organizationId}`);
  await page.getByRole("button", { name: "Impersonate sam@acme.com" }).click();
  await expect(page).toHaveURL(/\/api-keys$/);
  const remainingSeconds = async () => {
    const text = await page.getByRole("timer").innerText();
    const [minutes, seconds] = text.split(" ")[0]!.split(":").map(Number);
    return minutes! * 60 + seconds!;
  };
  await expect.poll(remainingSeconds).toBeGreaterThanOrEqual(895);
  await expect.poll(remainingSeconds).toBeLessThanOrEqual(900);
  elapsed += 60_000;
  await page.clock.fastForward(60_000);
  await expect.poll(remainingSeconds).toBeLessThanOrEqual(840);
  const beforeReload = await remainingSeconds();
  await page.reload();
  await expect.poll(remainingSeconds).toBeLessThanOrEqual(beforeReload);
  await expect.poll(remainingSeconds).toBeGreaterThanOrEqual(beforeReload - 5);
  elapsed += 14 * 60_000;
  await page.clock.fastForward(14 * 60_000);
  await expect(page).toHaveURL(/\/admin$/);
  await expect(page.getByRole("timer")).toHaveCount(0);
  expect(
    requests.filter(
      (request) => request.path === "/api/v1/admin/impersonations/stop",
    ),
  ).toHaveLength(1);
});

test("staff open an organization absent from their bootstrap memberships", async ({
  page,
}) => {
  const { me, requests } = await setup(page, { isStaff: true });
  me.organizations = [];
  await page.goto("/admin");
  await page.getByRole("link", { name: "Acme", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Acme", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Impersonate sam@acme.com" }),
  ).toBeVisible();
  expect(
    requests.some(
      (request) =>
        request.path === `/api/v1/admin/organizations/${organizationId}`,
    ),
  ).toBe(true);
});

test("impersonation, return and sign-out synchronize identity across tabs", async ({
  page,
  context,
}) => {
  await setup(page, { isStaff: true });
  await page.goto(`/admin/organizations/${organizationId}`);
  const other = await context.newPage();
  await other.goto("/models");
  await expect(other.getByRole("link", { name: "Admin portal" })).toBeVisible();

  await page.getByRole("button", { name: "Impersonate sam@acme.com" }).click();
  await expect(page).toHaveURL(/\/api-keys$/);
  for (const tab of [page, other]) {
    await expect(
      tab.getByRole("status").filter({ hasText: "Viewing as" }),
    ).toContainText("sam@acme.com");
    await expect(tab.getByRole("link", { name: "Admin portal" })).toHaveCount(
      0,
    );
  }

  await other.getByRole("button", { name: "Return to staff account" }).click();
  await expect(other).toHaveURL(/\/admin$/);
  for (const tab of [page, other]) {
    await expect(
      tab.locator('a[href="/admin"]').filter({ hasText: "Admin portal" }),
    ).toBeVisible();
    await expect(tab.getByText("Viewing as", { exact: false })).toHaveCount(0);
  }

  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Sign out", exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(other).toHaveURL(/\/login\?next=%2Fadmin$/);
});

test("an expired impersonation cold load restores staff before redirecting to login", async ({
  page,
}) => {
  const { me, requests } = await setup(page, { isStaff: true });
  await page.goto(`/admin/organizations/${organizationId}`);
  await page.getByRole("button", { name: "Impersonate sam@acme.com" }).click();
  await expect(page).toHaveURL(/\/api-keys$/);
  await expect(page.getByRole("timer")).toBeVisible();
  me.impersonation_expires_at = new Date(Date.now() - 1000).toISOString();

  await page.reload();

  await expect(page).toHaveURL(/\/admin$/);
  await expect(
    page.getByRole("heading", { name: "Admin portal", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("timer")).toHaveCount(0);
  expect(
    requests.filter(
      (request) => request.path === "/api/v1/admin/impersonations/stop",
    ),
  ).toHaveLength(1);
  expect(
    requests.filter((request) => request.path === "/api/auth/sign-out"),
  ).toHaveLength(0);
});

test("ordinary unauthenticated bootstrap does not attempt staff restoration", async ({
  page,
}) => {
  const { requests } = await setup(page, { signedIn: false });
  await page.goto("/api-keys");
  await expect(page).toHaveURL(/\/login$/);
  expect(
    requests.some(
      (request) => request.path === "/api/v1/admin/impersonations/stop",
    ),
  ).toBe(false);
});
