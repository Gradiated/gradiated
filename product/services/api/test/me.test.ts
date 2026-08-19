import { describe, expect, it } from "vitest";

import { createApp } from "../src/app.js";
import { authenticated, organizationId, user, workspaceId } from "./support.js";

describe("current user route", () => {
  it("rejects requests without a human session", async () => {
    const response = await createApp().request("/api/v1/me");

    expect(response.status).toBe(401);
    await expect(response.json()).resolves.toMatchObject({
      code: "unauthenticated",
    });
  });

  it("returns the current user and organization summaries", async () => {
    const app = createApp({
      auth: authenticated,
      services: {
        organizations: {
          createForUser: async () => {
            throw new Error("not used");
          },
          ensurePersonalForUser: async () => {
            throw new Error("not used");
          },
          listForUser: async () => [
            {
              id: organizationId,
              name: "Analytical Engines",
              status: "active",
              role: "owner",
              defaultWorkspaceId: workspaceId,
            },
          ],
        },
      },
    });
    const response = await app.request("/api/v1/me");

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({
      id: user.id,
      name: user.name,
      email: user.email,
      email_verified: true,
      image_url: null,
      created_at: "2026-08-16T12:00:00.000Z",
      organizations: [
        {
          id: organizationId,
          name: "Analytical Engines",
          status: "active",
          role: "owner",
          default_workspace_id: workspaceId,
        },
      ],
    });
  });
});
