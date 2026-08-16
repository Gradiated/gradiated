import { describe, expect, it } from "vitest";

import { createApp } from "../src/app.js";
import {
  authenticated,
  now,
  organizationId,
  user,
  workspaceId,
  workspaceService,
} from "./support.js";

describe("workspace routes", () => {
  it("lists workspaces explicitly for the selected organization", async () => {
    const app = createApp({
      auth: authenticated,
      services: { workspaces: workspaceService() },
    });
    const response = await app.request(
      `/api/v1/organizations/${organizationId}/workspaces`,
    );

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({
      data: [
        {
          id: workspaceId,
          organization_id: organizationId,
          name: "Default",
          is_default: true,
          archived_at: null,
          created_at: now.toISOString(),
          updated_at: now.toISOString(),
        },
      ],
      next_cursor: null,
    });
  });

  it("creates a workspace for the selected organization", async () => {
    let received:
      { userId: string; organizationId: string; name: string } | undefined;
    const service = workspaceService();
    const app = createApp({
      auth: authenticated,
      services: {
        workspaces: {
          ...service,
          createWorkspace: async (userId, receivedOrganizationId, input) => {
            received = {
              userId,
              organizationId: receivedOrganizationId,
              name: input.name,
            };
            return service.createWorkspace(
              userId,
              receivedOrganizationId,
              input,
            );
          },
        },
      },
    });
    const response = await app.request(
      `/api/v1/organizations/${organizationId}/workspaces`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "  Research  " }),
      },
    );

    expect(response.status).toBe(201);
    expect(received).toEqual({
      userId: user.id,
      organizationId,
      name: "Research",
    });
    await expect(response.json()).resolves.toMatchObject({
      organization_id: organizationId,
      name: "Research",
      is_default: false,
    });
  });
});
