import { afterEach, describe, expect, it, vi } from "vitest";

import {
  anonymous,
  authenticated,
  captureServiceLogs,
  createTestApp,
  expectProblem,
  organizationId,
  organizationSummary,
  sessionStoreDown,
  unauthenticatedProblem,
  user,
  workspaceId,
} from "./support.js";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("current user route", () => {
  it("rejects requests without a human session", async () => {
    const response = await createTestApp({ auth: anonymous }).request(
      "/api/v1/me",
    );

    await expectProblem(response, unauthenticatedProblem);
  });

  it("reports an unreachable session store as unavailable and logs its cause", async () => {
    const logs = captureServiceLogs();

    const response = await createTestApp({ auth: sessionStoreDown }).request(
      "/api/v1/me",
    );

    await expectProblem(response, {
      status: 503,
      code: "unavailable",
      type: "unavailable",
    });
    expect(logs.events()).toContainEqual(
      expect.objectContaining({
        level: "error",
        event: "request_problem",
        route: "/api/v1/me",
        status: 503,
        error_type: "SessionStoreError",
      }),
    );
  });

  it("returns the current user and organization summaries", async () => {
    const app = createTestApp({
      auth: authenticated,
      services: {
        organizations: { listForUser: async () => [organizationSummary] },
      },
    });

    const response = await app.request("/api/v1/me");

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({
      id: user.id,
      name: user.name,
      email: user.email,
      email_verified: true,
      impersonation_expires_at: null as string | null,
      impersonated_by: null,
      is_staff: false,
      company_email_domain: "example.com",
      image_url: null,
      created_at: "2026-08-16T12:00:00.000Z",
      organizations: [
        {
          id: organizationId,
          name: "Personal",
          slug: "personal",
          status: "active",
          role: "admin",
          default_workspace_id: workspaceId,
          auto_join_domain: null,
          onboarding_completed: false,
        },
      ],
    });
  });
});

it("reports staff access from the resolved session", async () => {
  const app = createTestApp({
    auth: {
      ...authenticated,
      resolveSession: async () => ({ ...user, isStaff: true }),
    },
    services: { organizations: { listForUser: async () => [] } },
  });
  const response = await app.request("/api/v1/me");
  expect(response.status).toBe(200);
  await expect(response.json()).resolves.toMatchObject({ is_staff: true });
});
