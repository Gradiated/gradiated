import { describe, expect, it, vi } from "vitest";

import { createApiClient } from "../src/api-client.js";
import { createApp } from "../src/app.js";
import { loadApiDocument } from "../src/openapi.js";
import { buildTools } from "../src/tools/definitions.js";

const workspaceId = "0198ae5a-2529-7c1a-801b-dc9d5f876a94";
const apiKey = `grad_${"a".repeat(43)}`;
const oauthToken = `grado_${"t".repeat(32)}`;
const tools = buildTools(loadApiDocument());

const testApp = () => {
  const fetchApi = vi.fn(
    async (input: URL | RequestInfo, init?: RequestInit) => {
      const url = new URL(String(input));
      const authorization = new Headers(init?.headers).get("authorization");
      if (
        authorization !== `Bearer ${apiKey}` &&
        authorization !== `Bearer ${oauthToken}`
      )
        return Response.json({ code: "unauthenticated" }, { status: 401 });

      if (url.pathname === "/api/v1/credentials/current")
        return Response.json({
          type: authorization.includes("grado_") ? "oauth_token" : "api_key",
          id: "0198ae6f-68b0-7644-812d-c4bf16a926e3",
          organization_id: "0198ae59-294a-73a9-9d2f-962449d34226",
          workspace_id: workspaceId,
          workspace_name: "Default",
          organization_name: "Acme",
          organization_slug: "acme",
          user: {
            id: "0198ae50-94d8-7d4d-a8be-9f9b44b8c774",
            name: "Ada Lovelace",
            email: "ada@example.com",
          },
        });

      return Response.json({
        path: url.pathname,
        query: url.search,
        body: init?.body ?? null,
      });
    },
  );
  const app = createApp({
    api: createApiClient("http://api.internal", fetchApi as typeof fetch),
    tools,
    publicUrl: "https://mcp.gradiated.com",
    consoleUrl: "https://console.gradiated.com",
    authorizationServer: "https://api.gradiated.com/api/auth",
  });

  return { app, fetchApi };
};

const rpc = (
  app: ReturnType<typeof testApp>["app"],
  method: string,
  params: unknown = {},
  headers: Record<string, string> = { Authorization: `Bearer ${apiKey}` },
) =>
  app.request("/mcp", {
    method: "POST",
    headers: {
      Accept: "application/json, text/event-stream",
      "Content-Type": "application/json",
      "Mcp-Protocol-Version": "2025-06-18",
      "X-Forwarded-For": "203.0.113.9",
      ...headers,
    },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
  });

describe("the MCP endpoint", () => {
  it("points a client without a credential at the OAuth metadata", async () => {
    const { app, fetchApi } = testApp();

    const response = await rpc(app, "tools/list", {}, {});

    expect(response.status).toBe(401);
    expect(response.headers.get("www-authenticate")).toBe(
      'Bearer resource_metadata="https://mcp.gradiated.com/.well-known/oauth-protected-resource/mcp", scope="mcp offline_access"',
    );
    expect(fetchApi).not.toHaveBeenCalled();
  });

  it("accepts an OAuth access token", async () => {
    const { app, fetchApi } = testApp();

    const { result } = await (
      await rpc(
        app,
        "tools/call",
        { name: "list_tasks", arguments: {} },
        {
          Authorization: `Bearer ${oauthToken}`,
        },
      )
    ).json();

    expect(JSON.parse(result.content[0].text).path).toBe(
      `/api/v1/workspaces/${workspaceId}/tasks`,
    );
    const [, init] = fetchApi.mock.calls.at(-1)!;
    expect(new Headers(init?.headers).get("authorization")).toBe(
      `Bearer ${oauthToken}`,
    );
  });

  it("rejects a key the API does not accept", async () => {
    const { app } = testApp();

    const response = await rpc(
      app,
      "tools/list",
      {},
      {
        Authorization: `Bearer grad_${"b".repeat(43)}`,
      },
    );

    expect(response.status).toBe(401);
  });

  it("initializes", async () => {
    const { app } = testApp();

    const response = await rpc(app, "initialize", {
      protocolVersion: "2025-06-18",
      capabilities: {},
      clientInfo: { name: "test", version: "1" },
    });

    expect(response.status).toBe(200);
    expect((await response.json()).result.serverInfo.name).toBe("gradiated");
  });

  it("lists the generated tools", async () => {
    const { app } = testApp();

    const { result } = await (await rpc(app, "tools/list")).json();

    expect(result.tools.map(({ name }: { name: string }) => name)).toEqual(
      tools.map(({ name }) => name),
    );
  });

  it("calls the API in the key's workspace with renamed arguments", async () => {
    const { app, fetchApi } = testApp();

    const { result } = await (
      await rpc(app, "tools/call", {
        name: "update_task",
        arguments: { task_name: "Billing questions", judge_model_id: "judge" },
      })
    ).json();

    expect(result.isError).toBeUndefined();
    expect(JSON.parse(result.content[0].text)).toEqual({
      path: `/api/v1/workspaces/${workspaceId}/tasks/Billing%20questions`,
      query: "",
      body: JSON.stringify({ judge_model_id: "judge" }),
    });
    const [, init] = fetchApi.mock.calls.at(-1)!;
    expect(init?.method).toBe("PATCH");
    expect(new Headers(init?.headers).get("x-forwarded-for")).toBe(
      "203.0.113.9",
    );
  });

  it("sends query arguments under their API names", async () => {
    const { app } = testApp();

    const { result } = await (
      await rpc(app, "tools/call", {
        name: "list_generations",
        arguments: { task_name: "support", limit: 5 },
      })
    ).json();

    expect(JSON.parse(result.content[0].text).query).toBe(
      "?limit=5&task_id=support",
    );
  });

  it.each([
    [{ name: "get_task", arguments: {} }, "Missing arguments: task_name."],
    [
      { name: "get_task", arguments: { task_name: "a", workspace_id: "b" } },
      "Unknown arguments: workspace_id.",
    ],
    [
      { name: "delete_everything", arguments: {} },
      "Unknown tool delete_everything.",
    ],
  ])("reports a bad call as a tool error %#", async (params, message) => {
    const { app } = testApp();

    const { result } = await (await rpc(app, "tools/call", params)).json();

    expect(result).toEqual({
      isError: true,
      content: [{ type: "text", text: message }],
    });
  });
});

describe("OAuth protected resource metadata", () => {
  it.each([
    "/.well-known/oauth-protected-resource/mcp",
    "/.well-known/oauth-protected-resource",
  ])("names the resource and its authorization server at %s", async (path) => {
    const { app } = testApp();

    const response = await app.request(path);

    expect(response.headers.get("access-control-allow-origin")).toBe("*");
    expect(await response.json()).toEqual({
      resource: "https://mcp.gradiated.com/mcp",
      resource_name: "Gradiated",
      resource_documentation: "https://mcp.gradiated.com/",
      authorization_servers: ["https://api.gradiated.com/api/auth"],
      scopes_supported: ["mcp", "offline_access"],
      bearer_methods_supported: ["header"],
    });
  });
});

describe("the index page", () => {
  it("explains how to connect and lists the tools", async () => {
    const { app } = testApp();

    const page = await (await app.request("/")).text();

    expect(page).toContain("https://mcp.gradiated.com/mcp");
    expect(page).toContain("claude mcp add --transport http gradiated");
    expect(page).toContain("add a custom connector with this URL");
    expect(page).toContain("<code>list_tasks</code>");
  });
});
