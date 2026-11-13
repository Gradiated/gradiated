import { ControlServiceError } from "@gradiated/control";
import { describe, expect, it, vi } from "vitest";

import {
  apiKeyId,
  apiKeySecret,
  authenticated,
  createTestApp,
  organizationId,
  user,
  workspaceId,
} from "./support.js";

const otherWorkspaceId = "0198ae5a-2529-7c1a-801b-dc9d5f876a95";
const grantId = "0198ae6f-68b0-7644-812d-c4bf16a926e4";
const oauthToken = `grado_${"t".repeat(32)}`;

const appWithCredentials = () => {
  const authenticateCredential = vi.fn(async (secret: string) => {
    if (secret === apiKeySecret)
      return {
        credential: "api_key" as const,
        credentialId: apiKeyId,
        organizationId,
        workspaceId,
        user,
      };
    if (secret === oauthToken)
      return {
        credential: "oauth_token" as const,
        credentialId: grantId,
        organizationId,
        workspaceId,
        user,
      };

    return undefined;
  });
  const describeCredential = vi.fn(async (secret: string) => {
    const owner = await authenticateCredential(secret);

    return (
      owner && {
        ...owner,
        workspaceName: "Default",
        organizationName: "Acme",
        organizationSlug: "acme",
      }
    );
  });
  const createOAuthInferenceCredential = vi.fn(async (secret: string) =>
    secret === oauthToken
      ? {
          apiKeyId: "0198ae6f-68b0-7644-812d-c4bf16a926e6",
          secret: `grad_${"m".repeat(43)}`,
          expiresAt: new Date("2026-11-13T13:00:00.000Z"),
        }
      : undefined,
  );
  const listTasks = vi.fn(async () => []);
  const listApiKeys = vi.fn(async () => []);
  const app = createTestApp({
    services: {
      workspaces: {
        authenticateCredential,
        describeCredential,
        createOAuthInferenceCredential,
        listApiKeys,
      },
      training: { listTasks },
    },
  });

  return { app, listTasks, listApiKeys };
};

const bearer = (secret: string) => ({
  headers: { Authorization: `Bearer ${secret}` },
});

describe.each([
  ["API key", apiKeySecret],
  ["OAuth access token", oauthToken],
])("a workspace %s on management routes", (_name, secret) => {
  it("acts as its member inside its workspace", async () => {
    const { app, listTasks } = appWithCredentials();

    const response = await app.request(
      `/api/v1/workspaces/${workspaceId}/tasks`,
      bearer(secret),
    );

    expect(response.status).toBe(200);
    expect(listTasks).toHaveBeenCalledWith(user.id, workspaceId);
  });

  it.each([
    ["GET", `/api/v1/workspaces/${otherWorkspaceId}/tasks`],
    ["GET", `/api/v1/workspaces/${workspaceId}/api-keys`],
    ["POST", `/api/v1/workspaces/${workspaceId}/playground-credentials`],
    ["DELETE", `/api/v1/workspaces/${workspaceId}`],
    ["GET", "/api/v1/me"],
  ])("does not authorize %s %s", async (method, path) => {
    const { app, listTasks, listApiKeys } = appWithCredentials();

    const response = await app.request(path, { method, ...bearer(secret) });

    expect(response.status).toBe(401);
    expect(listTasks).not.toHaveBeenCalled();
    expect(listApiKeys).not.toHaveBeenCalled();
  });
});

describe("workspace credentials", () => {
  it("accept an API key in the x-api-key header", async () => {
    const { app } = appWithCredentials();

    const response = await app.request(
      `/api/v1/workspaces/${workspaceId}/tasks`,
      { headers: { "x-api-key": apiKeySecret } },
    );

    expect(response.status).toBe(200);
  });

  it.each([`grad_${"b".repeat(43)}`, `grado_${"b".repeat(32)}`])(
    "reject unknown credential %s",
    async (secret) => {
      const { app } = appWithCredentials();

      const response = await app.request(
        `/api/v1/workspaces/${workspaceId}/tasks`,
        bearer(secret),
      );

      expect(response.status).toBe(401);
    },
  );
});

describe("GET /api/v1/credentials/current", () => {
  it.each([
    [apiKeySecret, "api_key", apiKeyId],
    [oauthToken, "oauth_token", grantId],
  ])("identifies the workspace of %s", async (secret, type, id) => {
    const { app } = appWithCredentials();

    const response = await app.request(
      "/api/v1/credentials/current",
      bearer(secret),
    );

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({
      type,
      id,
      organization_id: organizationId,
      workspace_id: workspaceId,
      workspace_name: "Default",
      organization_name: "Acme",
      organization_slug: "acme",
      user: { id: user.id, name: user.name, email: user.email },
    });
  });

  it("rejects a missing or unknown credential", async () => {
    const { app } = appWithCredentials();

    expect((await app.request("/api/v1/credentials/current")).status).toBe(401);
    expect(
      (
        await app.request(
          "/api/v1/credentials/current",
          bearer(`grad_${"b".repeat(43)}`),
        )
      ).status,
    ).toBe(401);
  });
});

describe("POST /api/v1/credentials/current/inference-keys", () => {
  const post = (secret?: string) =>
    appWithCredentials().app.request(
      "/api/v1/credentials/current/inference-keys",
      { method: "POST", ...(secret ? bearer(secret) : {}) },
    );

  it("gives an OAuth token an inference key", async () => {
    const response = await post(oauthToken);

    expect(response.status).toBe(201);
    expect(response.headers.get("cache-control")).toBe("no-store");
    expect(await response.json()).toEqual({
      secret: `grad_${"m".repeat(43)}`,
      expires_at: "2026-11-13T13:00:00.000Z",
    });
  });

  it("refuses API keys and unknown credentials", async () => {
    expect((await post(apiKeySecret)).status).toBe(403);
    expect((await post(`grado_${"u".repeat(32)}`)).status).toBe(401);
    expect((await post()).status).toBe(401);
  });
});

describe("PUT /api/v1/me/oauth-workspace", () => {
  const sessionId = "0198ae6f-68b0-7644-812d-c4bf16a926e5";

  const select = (
    resolveSession: () => Promise<typeof user | null>,
    selectOAuthWorkspace = vi.fn(async () => undefined),
    body: unknown = { workspace_id: workspaceId },
  ) =>
    createTestApp({
      auth: { ...authenticated, resolveSession },
      services: { workspaces: { selectOAuthWorkspace } },
    }).request("/api/v1/me/oauth-workspace", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });

  it("selects the workspace for the browser session", async () => {
    const selectOAuthWorkspace = vi.fn(async () => undefined);

    const response = await select(
      async () => ({ ...user, sessionId }),
      selectOAuthWorkspace,
    );

    expect(response.status).toBe(204);
    expect(selectOAuthWorkspace).toHaveBeenCalledWith(
      user.id,
      sessionId,
      workspaceId,
    );
  });

  it("requires a browser session, not a workspace credential", async () => {
    const selectOAuthWorkspace = vi.fn(async () => undefined);

    expect((await select(async () => null, selectOAuthWorkspace)).status).toBe(
      401,
    );
    expect((await select(async () => user, selectOAuthWorkspace)).status).toBe(
      401,
    );
    expect(selectOAuthWorkspace).not.toHaveBeenCalled();
  });

  it("reports a workspace the member cannot use", async () => {
    const response = await select(
      async () => ({ ...user, sessionId }),
      vi.fn(async () => {
        throw new ControlServiceError("not_found", "Workspace not found.");
      }),
    );

    expect(response.status).toBe(404);
  });

  it("rejects a malformed workspace ID", async () => {
    const response = await select(
      async () => ({ ...user, sessionId }),
      vi.fn(async () => undefined),
      { workspace_id: "default" },
    );

    expect(response.status).toBe(422);
  });
});
