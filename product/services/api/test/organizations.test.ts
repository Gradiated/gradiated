import { describe, expect, it } from "vitest";

import { createApp } from "../src/app.js";
import {
  authenticated,
  now,
  organizationId,
  user,
  workspaceId,
} from "./support.js";

describe("organization routes", () => {
  it("creates the organization aggregate for the current user", async () => {
    let received: { userId: string; name: string } | undefined;
    const app = createApp({
      auth: authenticated,
      services: {
        organizations: {
          listForUser: async () => [],
          createForUser: async (userId, name) => {
            received = { userId, name };
            return {
              id: organizationId,
              kind: "customer",
              name,
              status: "active",
              role: "owner",
              defaultWorkspaceId: workspaceId,
              createdAt: now,
              updatedAt: now,
            };
          },
        },
      },
    });
    const response = await app.request("/api/v1/organizations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "  Analytical Engines  " }),
    });

    expect(response.status).toBe(201);
    expect(received).toEqual({ userId: user.id, name: "Analytical Engines" });
    await expect(response.json()).resolves.toMatchObject({
      name: "Analytical Engines",
      role: "owner",
      default_workspace_id: workspaceId,
    });
  });
});
