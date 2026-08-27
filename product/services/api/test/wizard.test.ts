import { describe, expect, it } from "vitest";

import type { ApiServices } from "../src/types.js";
import { createApp } from "../src/app.js";
import {
  apiKeyId,
  authenticated,
  now,
  organizationId,
  user,
  workspaceId,
} from "./support.js";

const secretPattern = /^grad_[A-Za-z0-9_-]{43}$/;

function wizardApp() {
  const services = {
    organizations: {
      listForUser: async () => [
        {
          id: organizationId,
          name: "Personal",
          status: "active" as const,
          role: "owner" as const,
          defaultWorkspaceId: workspaceId,
        },
      ],
      createForUser: async () => {
        throw new Error("not used");
      },
      ensurePersonalForUser: async () => {
        throw new Error("not used");
      },
    },
    catalogBilling: {
      getBillingAccount: async () => ({
        organizationId,
        mode: "prepaid" as const,
        stripeCustomerId: null,
        balance: 5_000_000_000n,
        createdAt: now,
        updatedAt: now,
      }),
    },
    workspaces: {
      listWorkspaces: async () => [],
      createWorkspace: async () => {
        throw new Error("not used");
      },
      listApiKeys: async () => [],
      createApiKey: async (
        userId: string,
        receivedOrganizationId: string,
        receivedWorkspaceId: string,
        input: { name: string; expiresAt: Date | null },
      ) => ({
        apiKey: {
          id: apiKeyId,
          organizationId: receivedOrganizationId,
          workspaceId: receivedWorkspaceId,
          name: input.name,
          expiresAt: input.expiresAt,
          revokedAt: null,
          createdBy: userId,
          createdAt: now,
          updatedAt: now,
        },
        secret: `grad_${"a".repeat(43)}`,
      }),
      revokeApiKey: async () => undefined,
    },
  } as unknown as ApiServices;

  return {
    app: createApp({ auth: authenticated, services }),
  };
}

describe("wizard key route", () => {
  it("mints a local key on the default workspace and reports the balance", async () => {
    const { app } = wizardApp();

    const response = await app.request("/api/v1/wizard/key", {
      method: "POST",
    });

    expect(response.status).toBe(201);
    const body = await response.json();
    expect(body.secret).toMatch(secretPattern);
    expect(body.api_key.name).toBe("local");
    expect(body.api_key.created_by).toBe(user.id);
    expect(body.organization_id).toBe(organizationId);
    expect(body.workspace_id).toBe(workspaceId);
    expect(body.organization_name).toBe("Personal");
    expect(body.balance_nano_usd).toBe(5_000_000_000);
  });

  it("requires a session", async () => {
    const { app } = wizardApp();
    const unauthenticatedApp = createApp({
      auth: {
        handler: authenticated.handler,
        resolveSession: async () => null,
      },
      services: {},
    });

    const response = await unauthenticatedApp.request("/api/v1/wizard/key", {
      method: "POST",
    });

    expect(response.status).toBe(401);
    expect(response.headers.get("cache-control")).toBeNull();
  });

  it("reports 404 when the user has no organization", async () => {
    const app = createApp({
      auth: authenticated,
      services: {
        organizations: {
          listForUser: async () => [],
          createForUser: async () => {
            throw new Error("not used");
          },
          ensurePersonalForUser: async () => {
            throw new Error("not used");
          },
        },
      },
    });

    const response = await app.request("/api/v1/wizard/key", {
      method: "POST",
    });

    expect(response.status).toBe(404);
    await expect(response.json()).resolves.toMatchObject({
      code: "not_found",
    });
  });
});
