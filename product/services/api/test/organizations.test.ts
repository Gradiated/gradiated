import { ControlServiceError } from "@gradiated/control";
import { describe, expect, it } from "vitest";

import {
  anonymous,
  authenticated,
  controlServiceProblems,
  expectProblem,
  failWith,
  unauthenticatedProblem,
  validationProblem,
  createTestApp,
  createdOrganization,
  organizationSummary,
  postJson,
  user,
  workspaceId,
} from "./support.js";

describe("organization routes", () => {
  it("creates the organization aggregate for the current user", async () => {
    const received: unknown[] = [];
    const app = createTestApp({
      auth: authenticated,
      services: {
        organizations: {
          createForUser: async (userId, name) => {
            received.push({ userId, name });

            return { ...createdOrganization, name };
          },
        },
      },
    });

    const response = await postJson(app, "/api/v1/organizations", {
      name: "  Analytical Engines  ",
    });

    expect(response.status).toBe(201);
    expect(received).toEqual([{ userId: user.id, name: "Analytical Engines" }]);
    await expect(response.json()).resolves.toMatchObject({
      name: "Analytical Engines",
      role: "admin",
      default_workspace_id: workspaceId,
    });
  });

  it("requires a session", async () => {
    const response = await postJson(
      createTestApp({ auth: anonymous }),
      "/api/v1/organizations",
      { name: "Analytical Engines" },
    );

    await expectProblem(response, unauthenticatedProblem);
  });

  it("rejects an empty name before calling the service", async () => {
    const response = await postJson(
      createTestApp({ auth: authenticated }),
      "/api/v1/organizations",
      { name: "   " },
    );

    await expectProblem(response, validationProblem);
  });

  it.each(controlServiceProblems)("maps $code to $status", async (problem) => {
    const app = createTestApp({
      auth: authenticated,
      services: {
        organizations: {
          createForUser: failWith(
            new ControlServiceError(problem.code, "Rejected."),
          ),
        },
      },
    });

    const response = await postJson(app, "/api/v1/organizations", {
      name: "Analytical Engines",
    });

    await expectProblem(response, problem);
  });
});

it("PATCH validates and returns an organization name with the caller's admin role", async () => {
  const received: unknown[] = [];
  const app = createTestApp({
    auth: authenticated,
    services: {
      organizations: {
        updateForUser: async (userId, organizationId, input) => {
          received.push({ userId, organizationId, input });
          return {
            ...organizationSummary,
            name: input.name ?? organizationSummary.name,
            role: "admin",
          };
        },
      },
    },
  });
  const response = await app.request(
    `/api/v1/organizations/${createdOrganization.id}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "  Research  " }),
    },
  );
  expect(response.status).toBe(200);
  expect(received).toEqual([
    {
      userId: user.id,
      organizationId: createdOrganization.id,
      input: { name: "Research" },
    },
  ]);
  await expect(response.json()).resolves.toMatchObject({
    id: createdOrganization.id,
    name: "Research",
    role: "admin",
  });
});
it("PATCH completes onboarding and claims the email domain", async () => {
  const received: unknown[] = [];
  const app = createTestApp({
    auth: authenticated,
    services: {
      organizations: {
        updateForUser: async (_userId, _organizationId, input) => {
          received.push(input);
          return {
            ...organizationSummary,
            name: input.name ?? organizationSummary.name,
            autoJoinDomain: input.auto_join_domain ?? null,
            onboardingCompleted: true,
          };
        },
      },
    },
  });
  const response = await app.request(
    `/api/v1/organizations/${organizationSummary.id}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: "Acme",
        auto_join_domain: " Acme.com ",
        onboarding_completed: true,
      }),
    },
  );
  expect(response.status).toBe(200);
  expect(received).toEqual([
    { name: "Acme", auto_join_domain: "acme.com", onboarding_completed: true },
  ]);
  await expect(response.json()).resolves.toMatchObject({
    name: "Acme",
    auto_join_domain: "acme.com",
    onboarding_completed: true,
  });
});
it.each([
  {},
  { name: "   " },
  { name: "x".repeat(201) },
  { name: "Research", status: "suspended" },
  { auto_join_domain: "not a domain" },
  { auto_join_domain: "@acme.com" },
  { onboarding_completed: false },
])("rejects invalid organization settings %j", async (body) => {
  const response = await createTestApp({ auth: authenticated }).request(
    `/api/v1/organizations/${createdOrganization.id}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );
  await expectProblem(response, validationProblem);
});
it("requires authentication to rename an organization", async () => {
  const response = await createTestApp({ auth: anonymous }).request(
    `/api/v1/organizations/${createdOrganization.id}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "Research" }),
    },
  );
  await expectProblem(response, unauthenticatedProblem);
});

describe("staff organization provisioning", () => {
  it.each([
    ["anonymous", anonymous, 401],
    ["customer", authenticated, 403],
    [
      "unverified staff",
      {
        ...authenticated,
        resolveSession: async () => ({
          ...user,
          isStaff: true,
          emailVerified: false,
        }),
      },
      403,
    ],
  ] as const)("denies %s before provisioning", async (_name, auth, status) => {
    let called = false;
    const app = createTestApp({
      auth,
      services: {
        organizations: {
          createForUser: async () => {
            called = true;
            return createdOrganization;
          },
        },
      },
    });
    const response = await postJson(app, "/api/v1/admin/organizations", {
      name: "Customer",
    });
    expect(response.status).toBe(status);
    expect(called).toBe(false);
  });

  it("allows verified staff to prepare an organization with normal admin membership", async () => {
    const received: unknown[] = [];
    const app = createTestApp({
      auth: {
        ...authenticated,
        resolveSession: async () => ({ ...user, isStaff: true }),
      },
      services: {
        organizations: {
          createForUser: async (userId, name) => {
            received.push({ userId, name });
            return { ...createdOrganization, name };
          },
        },
      },
    });
    const response = await postJson(app, "/api/v1/admin/organizations", {
      name: " Customer ",
    });
    expect(response.status).toBe(201);
    expect(received).toEqual([{ userId: user.id, name: "Customer" }]);
    await expect(response.json()).resolves.toMatchObject({
      name: "Customer",
      role: "admin",
      default_workspace_id: workspaceId,
    });
  });

  it("does not allow staff privilege to be supplied in the request", async () => {
    const response = await postJson(
      createTestApp({ auth: authenticated }),
      "/api/v1/admin/organizations",
      { name: "Customer", is_staff: true },
    );
    expect(response.status).toBe(422);
  });
});

describe("staff organization search", () => {
  const staff = {
    ...authenticated,
    resolveSession: async () => ({ ...user, isStaff: true }),
  };

  it.each([
    anonymous,
    authenticated,
    {
      ...staff,
      resolveSession: async () => ({
        ...user,
        isStaff: true,
        emailVerified: false,
      }),
    },
  ])("denies unauthorized listing", async (auth) => {
    const response = await createTestApp({ auth }).request(
      "/api/v1/admin/organizations",
    );
    expect([401, 403]).toContain(response.status);
  });

  it("passes validated search and pagination to storage and bounds the response", async () => {
    const received: unknown[] = [];
    const app = createTestApp({
      auth: staff,
      services: {
        organizations: {
          listForUser: async (...args) => {
            received.push(args);
            return [
              organizationSummary,
              organizationSummary,
              organizationSummary,
            ];
          },
        },
      },
    });
    const response = await app.request(
      "/api/v1/admin/organizations?search=%20Acme%20&limit=2&offset=20",
    );
    expect(response.status).toBe(200);
    expect(received).toEqual([
      [user.id, undefined, { search: "Acme", limit: 3, offset: 20 }],
    ]);
    const body = await response.json();
    expect(body.data).toHaveLength(2);
    expect(body.has_more).toBe(true);
  });

  it.each([
    "limit=0",
    "limit=101",
    "offset=-1",
    "offset=1.5",
    "search=" + "x".repeat(201),
  ])("rejects invalid query %s", async (query) => {
    const response = await createTestApp({ auth: staff }).request(
      "/api/v1/admin/organizations?" + query,
    );
    expect(response.status).toBe(422);
  });
});

describe("staff organization details", () => {
  it("loads just the requested organization for verified staff", async () => {
    const received: unknown[] = [];
    const app = createTestApp({
      auth: {
        ...authenticated,
        resolveSession: async () => ({ ...user, isStaff: true }),
      },
      services: {
        organizations: {
          listForUser: async (...args) => {
            received.push(args);
            return [organizationSummary];
          },
        },
      },
    });
    const response = await app.request(
      `/api/v1/admin/organizations/${organizationSummary.id}`,
    );
    expect(response.status).toBe(200);
    expect(received).toEqual([[user.id, organizationSummary.id]]);
    await expect(response.json()).resolves.toMatchObject({
      id: organizationSummary.id,
      name: organizationSummary.name,
    });
  });

  it.each([
    [anonymous, 401],
    [authenticated, 403],
    [
      {
        ...authenticated,
        resolveSession: async () => ({
          ...user,
          isStaff: true,
          emailVerified: false,
        }),
      },
      403,
    ],
    [
      {
        ...authenticated,
        resolveSession: async () => ({
          ...user,
          isStaff: true,
          impersonatedBy: user.id,
        }),
      },
      403,
    ],
  ] as const)(
    "denies organization details without verified, non-impersonated staff access",
    async (auth, status) => {
      let queried = false;
      const app = createTestApp({
        auth,
        services: {
          organizations: {
            listForUser: async () => {
              queried = true;
              return [organizationSummary];
            },
          },
        },
      });
      expect(
        (
          await app.request(
            `/api/v1/admin/organizations/${organizationSummary.id}`,
          )
        ).status,
      ).toBe(status);
      expect(queried).toBe(false);
    },
  );

  it("reports a missing customer organization", async () => {
    const app = createTestApp({
      auth: {
        ...authenticated,
        resolveSession: async () => ({ ...user, isStaff: true }),
      },
      services: { organizations: { listForUser: async () => [] } },
    });
    expect(
      (
        await app.request(
          `/api/v1/admin/organizations/${organizationSummary.id}`,
        )
      ).status,
    ).toBe(404);
  });
});
