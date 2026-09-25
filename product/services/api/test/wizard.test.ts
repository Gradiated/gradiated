import { ControlServiceError } from "@gradiated/control";
import { describe, expect, it } from "vitest";

import {
  anonymous,
  apiKeyRecord,
  apiKeySecret,
  authenticated,
  billingAccountRecord,
  createTestApp,
  expectProblem,
  failWith,
  unauthenticatedProblem,
  organizationId,
  organizationSummary,
  user,
  workspaceId,
  type ServiceOverrides,
} from "./support.js";

const wizardKeyPath = "/api/v1/wizard/key";

const wizardServices: ServiceOverrides = {
  organizations: { listForUser: async () => [organizationSummary] },
  catalogBilling: {
    getBillingAccount: async () => ({
      ...billingAccountRecord,
      balance: 5_000_000_000n,
    }),
  },
  workspaces: {
    createApiKey: async (userId, receivedWorkspaceId, input) => ({
      apiKey: {
        ...apiKeyRecord,
        organizationId,
        workspaceId: receivedWorkspaceId,
        name: input.name,
        expiresAt: input.expiresAt,
        createdBy: userId,
      },
      secret: apiKeySecret,
    }),
  },
};

const mintKey = (services: ServiceOverrides = wizardServices) =>
  createTestApp({ auth: authenticated, services }).request(wizardKeyPath, {
    method: "POST",
  });

describe("wizard key route", () => {
  it("mints a local key on the default workspace and reports the balance", async () => {
    const response = await mintKey();

    expect(response.status).toBe(201);
    expect(response.headers.get("cache-control")).toBe("no-store");
    await expect(response.json()).resolves.toMatchObject({
      api_key: { name: "local", created_by: user.id, expires_at: null },
      secret: apiKeySecret,
      organization_id: organizationId,
      workspace_id: workspaceId,
      organization_name: "Personal",
      balance_nano_usd: 5_000_000_000,
    });
  });

  it("requires a session", async () => {
    const response = await createTestApp({ auth: anonymous }).request(
      wizardKeyPath,
      { method: "POST" },
    );

    await expectProblem(response, unauthenticatedProblem);
    expect(response.headers.get("cache-control")).toBeNull();
  });

  it("reports 404 when the user has no organization", async () => {
    const response = await mintKey({
      organizations: { listForUser: async () => [] },
    });

    expect(response.status).toBe(404);
    await expect(response.json()).resolves.toMatchObject({
      type: "https://gradiated.com/problems/not-found",
      title: "No organization",
      code: "not_found",
    });
  });

  it.each([
    {
      name: "a missing billing account",
      services: {
        catalogBilling: {
          getBillingAccount: failWith(
            new ControlServiceError("not_found", "Rejected."),
          ),
        },
      },
      problem: { status: 404, code: "not_found", type: "not-found" },
    },
    {
      name: "a forbidden organization",
      services: {
        catalogBilling: {
          getBillingAccount: failWith(
            new ControlServiceError("forbidden", "Rejected."),
          ),
        },
      },
      problem: { status: 403, code: "forbidden", type: "forbidden" },
    },
    {
      name: "unavailable key storage",
      services: {
        workspaces: {
          createApiKey: failWith(
            new ControlServiceError("unavailable", "Rejected."),
          ),
        },
      },
      problem: { status: 503, code: "unavailable", type: "unavailable" },
    },
  ])("reports $name as $problem.status", async ({ services, problem }) => {
    const response = await mintKey({ ...wizardServices, ...services });

    await expectProblem(response, problem);
  });
});
