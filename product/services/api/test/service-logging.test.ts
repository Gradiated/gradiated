import { describe, expect, it } from "vitest";

import {
  anonymous,
  apiKeyId,
  apiKeyRecord,
  apiKeySecret,
  authenticated,
  captureServiceLogs,
  createTestApp,
  organizationId,
  postJson,
  workspaceId,
} from "./support.js";

const apiKeysPath = `/api/v1/organizations/${organizationId}/workspaces/${workspaceId}/api-keys`;
const apiKeyPath = `${apiKeysPath}/${apiKeyId}`;

const completedRequest = (logs: ReturnType<typeof captureServiceLogs>) =>
  logs.events().find((event) => event.event === "request_completed");

describe("request logs", () => {
  it("keep verified resource IDs without logging credentials or identities", async () => {
    const logs = captureServiceLogs();
    const app = createTestApp({
      auth: authenticated,
      services: { workspaces: { revokeApiKey: async () => undefined } },
    });

    await app.request(apiKeyPath, {
      method: "DELETE",
      headers: { authorization: "Bearer DO_NOT_LOG_THIS" },
    });

    expect(completedRequest(logs)).toMatchObject({
      organization_id: organizationId,
      workspace_id: workspaceId,
      api_key_id: apiKeyId,
      context_source: "authenticated_session_requested_resource",
      status: 204,
    });
    expect(logs.lines().join("\n")).not.toMatch(
      /DO_NOT_LOG_THIS|ada@example|Ada Lovelace/,
    );
  });

  it("name a created API key without logging its secret or name", async () => {
    const logs = captureServiceLogs();
    const app = createTestApp({
      auth: authenticated,
      services: {
        workspaces: {
          createApiKey: async () => ({
            apiKey: apiKeyRecord,
            secret: apiKeySecret,
          }),
        },
      },
    });

    const response = await postJson(app, apiKeysPath, {
      name: "PRIVATE_KEY_NAME",
    });

    expect(response.status).toBe(201);
    expect(completedRequest(logs)).toMatchObject({ api_key_id: apiKeyId });
    expect(logs.lines().join("\n")).not.toContain(apiKeySecret);
    expect(logs.lines().join("\n")).not.toContain("PRIVATE_KEY_NAME");
  });

  it("carry no resource IDs for an unauthenticated request", async () => {
    const logs = captureServiceLogs();
    const app = createTestApp({ auth: anonymous });

    await app.request(apiKeyPath, { method: "DELETE" });

    const event = completedRequest(logs);
    expect(event?.organization_id).toBeUndefined();
    expect(event?.workspace_id).toBeUndefined();
    expect(event?.api_key_id).toBeUndefined();
  });
});
