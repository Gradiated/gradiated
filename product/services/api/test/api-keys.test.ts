import { ControlServiceError } from "@gradiated/control";
import { describe, expect, it } from "vitest";

import {
  anonymous,
  apiKeyId,
  apiKeyRecord,
  apiKeySecret,
  authenticated,
  controlServiceProblems,
  createTestApp,
  expectProblem,
  failWith,
  now,
  organizationId,
  postJson,
  unauthenticatedProblem,
  user,
  validationProblem,
  workspaceId,
  type TestApp,
} from "./support.js";

const apiKeysPath = `/api/v1/organizations/${organizationId}/workspaces/${workspaceId}/api-keys`;
const apiKeyPath = `${apiKeysPath}/${apiKeyId}`;

const operations: {
  name: string;
  method: "createApiKey" | "listApiKeys" | "revokeApiKey";
  send: (app: TestApp) => Response | Promise<Response>;
}[] = [
  {
    name: "create",
    method: "createApiKey",
    send: (app) => postJson(app, apiKeysPath, { name: "Production" }),
  },
  {
    name: "list",
    method: "listApiKeys",
    send: (app) => app.request(apiKeysPath),
  },
  {
    name: "revoke",
    method: "revokeApiKey",
    send: (app) => app.request(apiKeyPath, { method: "DELETE" }),
  },
];

describe("API-key routes", () => {
  it("returns a newly created secret exactly once", async () => {
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

    const response = await postJson(app, apiKeysPath, { name: "Production" });

    expect(response.status).toBe(201);
    expect(response.headers.get("cache-control")).toBe("no-store");
    await expect(response.json()).resolves.toMatchObject({
      api_key: { id: apiKeyId, name: "Production", revoked_at: null },
      secret: apiKeySecret,
    });
  });

  it("passes the requested expiry to the service as a date", async () => {
    const expiresAt = "2027-01-01T00:00:00.000Z";
    const received: unknown[] = [];
    const app = createTestApp({
      auth: authenticated,
      services: {
        workspaces: {
          createApiKey: async (...input) => {
            received.push(input);

            return { apiKey: apiKeyRecord, secret: apiKeySecret };
          },
        },
      },
    });

    const response = await postJson(app, apiKeysPath, {
      name: "Production",
      expires_at: expiresAt,
    });

    expect(response.status).toBe(201);
    expect(received).toEqual([
      [
        user.id,
        organizationId,
        workspaceId,
        { name: "Production", expiresAt: new Date(expiresAt) },
      ],
    ]);
  });

  it("lists key metadata without secrets", async () => {
    const app = createTestApp({
      auth: authenticated,
      services: { workspaces: { listApiKeys: async () => [apiKeyRecord] } },
    });

    const response = await app.request(apiKeysPath);

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({
      data: [
        {
          id: apiKeyId,
          organization_id: organizationId,
          workspace_id: workspaceId,
          name: "Production",
          expires_at: null,
          revoked_at: null,
          created_by: user.id,
          created_at: now.toISOString(),
          updated_at: now.toISOString(),
        },
      ],
      next_cursor: null,
    });
  });

  it("revokes a key with an empty 204 response", async () => {
    const received: unknown[] = [];
    const app = createTestApp({
      auth: authenticated,
      services: {
        workspaces: {
          revokeApiKey: async (...input) => {
            received.push(input);
          },
        },
      },
    });

    const response = await app.request(apiKeyPath, { method: "DELETE" });

    expect(response.status).toBe(204);
    await expect(response.text()).resolves.toBe("");
    expect(received).toEqual([
      [user.id, organizationId, workspaceId, apiKeyId],
    ]);
  });

  it.each(
    operations.flatMap((operation) =>
      controlServiceProblems.map((problem) => ({ ...operation, problem })),
    ),
  )(
    "maps $problem.code on $name to $problem.status",
    async ({ method, send, problem }) => {
      const app = createTestApp({
        auth: authenticated,
        services: {
          workspaces: {
            [method]: failWith(
              new ControlServiceError(problem.code, "Rejected."),
            ),
          },
        },
      });

      await expectProblem(await send(app), problem);
    },
  );

  it.each(operations)("requires a session to $name", async ({ send }) => {
    const response = await send(createTestApp({ auth: anonymous }));

    await expectProblem(response, unauthenticatedProblem);
    expect(response.headers.get("cache-control")).toBeNull();
  });

  it("rejects an invalid body before calling the service", async () => {
    const app = createTestApp({ auth: authenticated });

    const response = await postJson(app, apiKeysPath, { name: "" });

    await expectProblem(response, validationProblem);
  });
});
