import { describe, expect, it, vi } from "vitest";

import {
  apiKeyId,
  organizationId,
  apiKeySecret,
  createTestApp,
  user,
  workspaceId,
} from "./support.js";

const otherWorkspaceId = "0198ae5a-2529-7c1a-801b-dc9d5f876a95";

const appWithKey = () => {
  const authenticateApiKey = vi.fn(async (secret: string) =>
    secret === apiKeySecret
      ? { apiKeyId, organizationId, workspaceId, user }
      : undefined,
  );
  const listTasks = vi.fn(async () => []);
  const listApiKeys = vi.fn(async () => []);
  const app = createTestApp({
    services: {
      workspaces: { authenticateApiKey, listApiKeys },
      training: { listTasks },
    },
  });

  return { app, authenticateApiKey, listTasks, listApiKeys };
};

const bearer = (secret = apiKeySecret) => ({
  headers: { Authorization: `Bearer ${secret}` },
});

describe("workspace API keys on management routes", () => {
  it("act as the key's creator inside its workspace", async () => {
    const { app, listTasks } = appWithKey();

    const response = await app.request(
      `/api/v1/workspaces/${workspaceId}/tasks`,
      bearer(),
    );

    expect(response.status).toBe(200);
    expect(listTasks).toHaveBeenCalledWith(user.id, workspaceId);
  });

  it("accept the x-api-key header", async () => {
    const { app } = appWithKey();

    const response = await app.request(
      `/api/v1/workspaces/${workspaceId}/tasks`,
      { headers: { "x-api-key": apiKeySecret } },
    );

    expect(response.status).toBe(200);
  });

  it.each([
    ["GET", `/api/v1/workspaces/${otherWorkspaceId}/tasks`],
    ["GET", `/api/v1/workspaces/${workspaceId}/api-keys`],
    ["POST", `/api/v1/workspaces/${workspaceId}/playground-credentials`],
    ["DELETE", `/api/v1/workspaces/${workspaceId}`],
    ["GET", "/api/v1/me"],
  ])("do not authorize %s %s", async (method, path) => {
    const { app, listTasks, listApiKeys } = appWithKey();

    const response = await app.request(path, { method, ...bearer() });

    expect(response.status).toBe(401);
    expect(listTasks).not.toHaveBeenCalled();
    expect(listApiKeys).not.toHaveBeenCalled();
  });

  it("reject an unknown key", async () => {
    const { app } = appWithKey();

    const response = await app.request(
      `/api/v1/workspaces/${workspaceId}/tasks`,
      bearer(`grad_${"b".repeat(43)}`),
    );

    expect(response.status).toBe(401);
  });
});

describe("GET /api/v1/api-keys/current", () => {
  it("identifies the key's workspace", async () => {
    const { app } = appWithKey();

    const response = await app.request("/api/v1/api-keys/current", bearer());

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({
      id: apiKeyId,
      organization_id: organizationId,
      workspace_id: workspaceId,
    });
  });

  it("rejects a missing or unknown key", async () => {
    const { app } = appWithKey();

    expect((await app.request("/api/v1/api-keys/current")).status).toBe(401);
    expect(
      (
        await app.request(
          "/api/v1/api-keys/current",
          bearer(`grad_${"b".repeat(43)}`),
        )
      ).status,
    ).toBe(401);
  });
});
