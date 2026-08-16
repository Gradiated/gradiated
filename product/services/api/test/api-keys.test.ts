import { describe, expect, it } from "vitest";

import { createApp } from "../src/app.js";
import {
  apiKeyId,
  authenticated,
  organizationId,
  workspaceId,
  workspaceService,
} from "./support.js";

describe("API-key routes", () => {
  it("returns a newly created secret exactly once", async () => {
    const app = createApp({
      auth: authenticated,
      services: { workspaces: workspaceService() },
    });
    const response = await app.request(
      `/api/v1/organizations/${organizationId}/workspaces/${workspaceId}/api-keys`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "Production" }),
      },
    );

    expect(response.status).toBe(201);
    expect(response.headers.get("cache-control")).toBe("no-store");
    await expect(response.json()).resolves.toMatchObject({
      api_key: {
        id: apiKeyId,
        name: "Production",
        revoked_at: null,
      },
      secret: `grad_${"a".repeat(43)}`,
    });
  });
});
