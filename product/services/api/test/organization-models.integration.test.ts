import { randomUUID } from "node:crypto";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import {
  applyCatalog,
  createCatalogBillingService,
  type ControlDatabase,
} from "@gradiated/control";

import {
  createTestDatabase,
  type TestDatabase,
} from "../../../packages/control/test/support/postgres.js";
import {
  modelInput,
  ownedModelDefinition,
  seedMember,
} from "../../../packages/control/test/support/fixtures.js";
import { createApiClient } from "../../mcp/src/api-client.js";
import { createApp as createMcpApp } from "../../mcp/src/app.js";
import { createCredentialCache } from "../../mcp/src/cache.js";
import { createCredentials } from "../../mcp/src/credentials.js";
import { loadApiDocument } from "../../mcp/src/openapi.js";
import { buildTools } from "../../mcp/src/tools/definitions.js";
import { createTestApp } from "./support.js";

const apiKey = `grad_${"a".repeat(43)}`;

// Every TypeScript listing of hosted models, over a real migrated catalog. The
// gateway's /v1/models has the same check in its Rust tests.
describe("organization-owned models in listings", () => {
  let testDatabase: TestDatabase;
  let owned: string;
  let publicModel: string;

  beforeAll(async () => {
    testDatabase = await createTestDatabase();
    const database = testDatabase.database as unknown as ControlDatabase;
    const owner = await seedMember(testDatabase.database, { role: "admin" });
    const slug = `owner-${randomUUID().slice(0, 8)}`;
    await testDatabase.pool.query(
      "update organizations set slug = $1 where id = $2",
      [slug, owner.organizationId],
    );
    const definition = ownedModelDefinition(slug);
    const listed = modelInput({ id: `public/${randomUUID()}` });
    owned = definition.id;
    publicModel = listed.id;

    const result = await applyCatalog(database, [definition, listed]);
    expect(result.skipped).toEqual([]);
  });

  afterAll(() => testDatabase.dispose());

  const api = () =>
    createTestApp({
      services: {
        catalogBilling: createCatalogBillingService(
          testDatabase.database as unknown as ControlDatabase,
        ),
      },
    });

  const ids = (body: unknown) =>
    (body as { data: { id: string }[] }).data.map((model) => model.id);

  it("leaves it out of the public Models API, the website's source", async () => {
    const response = await api().request("/api/v1/models");

    expect(response.status).toBe(200);
    const listed = ids(await response.json());
    expect(listed).toContain(publicModel);
    expect(listed).not.toContain(owned);
  });

  it("leaves it out of MCP list_models", async () => {
    const app = api();
    const fetchApi = (async (input: URL | RequestInfo, init?: RequestInit) => {
      const url = new URL(String(input));
      if (url.pathname === "/api/v1/credentials/current")
        return Response.json({
          type: "api_key",
          id: randomUUID(),
          organization_id: randomUUID(),
          workspace_id: randomUUID(),
          workspace_name: "Default",
          organization_name: "Other",
          organization_slug: "other",
          user: { id: randomUUID(), name: "Ada", email: "ada@example.com" },
        });

      return app.request(`${url.pathname}${url.search}`, init);
    }) as typeof fetch;
    const client = createApiClient(
      "http://api.internal",
      "http://inference.internal",
      fetchApi,
    );
    const mcp = createMcpApp({
      api: client,
      tools: buildTools(loadApiDocument()),
      credentials: createCredentials(client, createCredentialCache(undefined)),
      publicUrl: "https://mcp.gradiated.com",
      consoleUrl: "https://console.gradiated.com",
      authorizationServer: "https://api.gradiated.com/api/auth",
    });

    const response = await mcp.request("/mcp", {
      method: "POST",
      headers: {
        Accept: "application/json, text/event-stream",
        "Content-Type": "application/json",
        "Mcp-Protocol-Version": "2025-06-18",
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        jsonrpc: "2.0",
        id: 1,
        method: "tools/call",
        params: { name: "list_models", arguments: {} },
      }),
    });
    const { result } = (await response.json()) as {
      result: {
        isError?: boolean;
        content: { text: string }[];
        structuredContent?: unknown;
      };
    };

    expect(result.isError).not.toBe(true);
    const listed = ids(
      result.structuredContent ?? JSON.parse(result.content[0]!.text),
    );
    expect(listed).toContain(publicModel);
    expect(listed).not.toContain(owned);
  });
});
