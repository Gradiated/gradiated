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
      role: "owner",
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
