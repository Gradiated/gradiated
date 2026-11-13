import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import type { Transport } from "@modelcontextprotocol/sdk/shared/transport.js";
import { describe, expect, it, vi } from "vitest";

import { createApiClient, MAX_RESULT_CHARACTERS } from "../src/api-client.js";
import { createApp } from "../src/app.js";
import { createCredentialCache, type CacheStore } from "../src/cache.js";
import { createCredentials } from "../src/credentials.js";
import { createMcpMetrics } from "../src/metrics.js";
import { loadApiDocument } from "../src/openapi.js";
import { buildTools } from "../src/tools/definitions.js";

const workspaceId = "0198ae5a-2529-7c1a-801b-dc9d5f876a94";
const apiKey = `grad_${"a".repeat(43)}`;
const oauthToken = `grado_${"t".repeat(32)}`;
const tools = buildTools(loadApiDocument());

const identity = (type: "api_key" | "oauth_token") => ({
  type,
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

const version = {
  id: "0198ae70-0000-7000-8000-000000000001",
  name: "v2",
  task: "support",
  training_run_id: null,
  base_model_id: "qwen/qwen3-8b",
  adapter: {
    format: "peft_lora",
    artifact_uri: "s3://bucket/adapter",
    sha256: "a".repeat(64),
    size_bytes: 1024,
    rank: 16,
  },

  status: "available",
  is_production: false,
  created_at: "2026-11-13T12:00:00.000Z",
};

type Handler = (
  url: URL,
  init: RequestInit | undefined,
) => Response | Promise<Response>;

const memoryStore = () => {
  const entries = new Map<string, string>();
  const store: CacheStore = {
    get: async (key) => entries.get(key) ?? null,
    set: async (key, value) => {
      entries.set(key, value);
    },
    delete: async (key) => {
      entries.delete(key);
    },
  };

  return { entries, store };
};

const testApp = ({
  api = () => undefined,
  inference = () => Response.json({ id: "chatcmpl-1" }),
  credentialStatus = 200,
}: {
  api?: (url: URL, init: RequestInit | undefined) => Response | undefined;
  inference?: Handler;
  credentialStatus?: number;
} = {}) => {
  let inferenceKeys = 0;
  const fetchApi = vi.fn(
    async (input: URL | RequestInfo, init?: RequestInit) => {
      const url = new URL(String(input));
      const authorization = new Headers(init?.headers).get("authorization");

      if (url.host === "inference.internal") return inference(url, init);

      if (
        authorization !== `Bearer ${apiKey}` &&
        authorization !== `Bearer ${oauthToken}`
      )
        return Response.json({ code: "unauthenticated" }, { status: 401 });

      if (credentialStatus !== 200)
        return new Response(null, { status: credentialStatus });
      if (url.pathname === "/api/v1/credentials/current")
        return Response.json(
          identity(
            authorization.includes("grado_") ? "oauth_token" : "api_key",
          ),
        );
      if (url.pathname === "/api/v1/credentials/current/inference-keys")
        return Response.json(
          {
            secret: `grad_${String(++inferenceKeys).repeat(43)}`,
            expires_at: new Date(Date.now() + 3_600_000).toISOString(),
          },
          { status: 201 },
        );

      return (
        api(url, init) ??
        Response.json({
          path: url.pathname,
          query: url.search,
          body: init?.body ?? null,
        })
      );
    },
  );
  const { entries, store } = memoryStore();
  const metrics = createMcpMetrics({ collectProcessMetrics: false });
  const client = createApiClient(
    "http://api.internal",
    "http://inference.internal",
    fetchApi as typeof fetch,
  );
  const app = createApp({
    api: client,
    tools,
    credentials: createCredentials(
      client,
      createCredentialCache(store, metrics.cache),
      metrics,
    ),
    metrics,
    publicUrl: "https://mcp.gradiated.com",
    consoleUrl: "https://console.gradiated.com",
    authorizationServer: "https://api.gradiated.com/api/auth",
  });

  return { app, fetchApi, entries, metrics };
};

type App = ReturnType<typeof testApp>["app"];

const rpc = (
  app: App,
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

const callTool = async (
  app: App,
  name: string,
  args: Record<string, unknown> = {},
  credential = apiKey,
) =>
  (
    await (
      await rpc(
        app,
        "tools/call",
        { name, arguments: args },
        { Authorization: `Bearer ${credential}` },
      )
    ).json()
  ).result;

const echoed = (result: { content: { text: string }[] }) =>
  JSON.parse(result.content[0]!.text) as {
    path: string;
    query: string;
    body: string | null;
  };

const calls = (
  fetchApi: ReturnType<typeof testApp>["fetchApi"],
  path: string,
) =>
  fetchApi.mock.calls.filter(
    ([input]) => new URL(String(input)).pathname === path,
  );

describe("authentication", () => {
  it("points a client without a credential at the OAuth metadata", async () => {
    const { app, fetchApi } = testApp();

    const response = await rpc(app, "tools/list", {}, {});

    expect(response.status).toBe(401);
    expect(response.headers.get("www-authenticate")).toBe(
      'Bearer resource_metadata="https://mcp.gradiated.com/.well-known/oauth-protected-resource/mcp", scope="mcp offline_access"',
    );
    expect(fetchApi).not.toHaveBeenCalled();
  });

  it("rejects a key the API does not accept", async () => {
    const { app } = testApp();

    const response = await rpc(
      app,
      "tools/list",
      {},
      { Authorization: `Bearer grad_${"b".repeat(43)}` },
    );

    expect(response.status).toBe(401);
  });

  it("answers 503 when the API cannot check the credential", async () => {
    const { app, metrics } = testApp({ credentialStatus: 502 });

    expect((await rpc(app, "tools/list")).status).toBe(503);
    expect(await metrics.registry.metrics()).toContain(
      'gradiated_mcp_authentications_total{result="error",service="mcp"} 1',
    );
  });

  it("caches the credential's identity, encrypted, across requests", async () => {
    const { app, fetchApi, entries } = testApp();

    await callTool(app, "list_tasks");
    await callTool(app, "list_tasks");

    expect(calls(fetchApi, "/api/v1/credentials/current")).toHaveLength(1);
    const stored = [...entries.values()].join("");
    expect(stored).not.toContain(workspaceId);
    expect(stored).not.toContain("ada@example.com");
    expect([...entries.keys()].join("")).not.toContain(apiKey.slice(5));
  });

  it("acts with an OAuth access token in its workspace", async () => {
    const { app, fetchApi } = testApp();

    const result = await callTool(app, "list_tasks", {}, oauthToken);

    expect(echoed(result).path).toBe(`/api/v1/workspaces/${workspaceId}/tasks`);
    const [, init] = fetchApi.mock.calls.at(-1)!;
    expect(new Headers(init?.headers).get("authorization")).toBe(
      `Bearer ${oauthToken}`,
    );
  });
});

describe("the MCP endpoint", () => {
  it("initializes with tools and prompts", async () => {
    const { app } = testApp();

    const response = await rpc(app, "initialize", {
      protocolVersion: "2025-06-18",
      capabilities: {},
      clientInfo: { name: "test", version: "1" },
    });

    const { result } = await response.json();
    expect(result.serverInfo.name).toBe("gradiated");
    expect(result.capabilities).toMatchObject({ tools: {}, prompts: {} });
  });

  it("lists the generated tools with output schemas", async () => {
    const { app } = testApp();

    const { result } = await (await rpc(app, "tools/list")).json();

    expect(result.tools.map(({ name }: { name: string }) => name)).toEqual(
      tools.map(({ name }) => name),
    );
    expect(
      result.tools.find(({ name }: { name: string }) => name === "list_tasks")
        .outputSchema.type,
    ).toBe("object");
  });

  it("returns structured content that a client validates against the output schema", async () => {
    const { app } = testApp({
      api: (url) =>
        url.pathname.endsWith("/tasks/support/versions/v2")
          ? Response.json(version)
          : undefined,
    });
    const client = new Client({ name: "test", version: "1" });
    const transport = new StreamableHTTPClientTransport(
      new URL("https://mcp.gradiated.com/mcp"),
      {
        fetch: async (input, init) => app.request(String(input), init),
        requestInit: { headers: { Authorization: `Bearer ${apiKey}` } },
      },
    );
    // The SDK's transport types disagree under exactOptionalPropertyTypes.
    await client.connect(transport as Transport);
    await client.listTools();

    const result = await client.callTool({
      name: "get_task_version",
      arguments: { task_name: "support", version: "v2" },
    });

    expect(result.structuredContent).toEqual(version);
    await client.close();
  });

  it("calls the API in the credential's workspace with renamed arguments", async () => {
    const { app, fetchApi } = testApp();

    const result = await callTool(app, "update_task", {
      task_name: "Billing questions",
      judge_model_id: "judge",
    });

    expect(result.isError).toBeUndefined();
    expect(echoed(result)).toEqual({
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

  it("names tasks, versions and files rather than taking their IDs", async () => {
    const { app } = testApp();

    expect(
      echoed(
        await callTool(app, "read_task_version_file", {
          task_name: "support",
          version: "v2",
          file: "report.md",
        }),
      ).path,
    ).toBe(
      `/api/v1/workspaces/${workspaceId}/tasks/support/versions/v2/files/report.md/content`,
    );
    expect(
      echoed(
        await callTool(app, "promote_task_version", {
          task_name: "support",
          version: "v2",
        }),
      ).body,
    ).toBe(JSON.stringify({ version_id: "v2" }));
  });

  it("reads a generation by its task name and never offers a content reference", async () => {
    const { app } = testApp();
    const generation = "0198ae70-0000-7000-8000-000000000002";

    const result = await callTool(app, "get_generation", {
      generation_id: generation,
      task_name: "support",
    });

    expect(echoed(result).query).toBe("?task_id=support");
    expect(
      (await callTool(app, "get_generation", { generation_id: generation }))
        .content[0].text,
    ).toBe("Missing arguments: task_name.");
  });

  it("sends query arguments under their API names and types", async () => {
    const { app } = testApp();

    const result = await callTool(app, "list_generations", {
      task_name: "support",
      limit: 5,
    });

    expect(echoed(result).query).toBe("?limit=5&task_id=support");
  });

  it("passes an API error through as a tool error", async () => {
    const problem = { code: "not_found", detail: "The task was not found." };
    const { app, metrics } = testApp({
      api: () => Response.json(problem, { status: 404 }),
    });

    const result = await callTool(app, "get_task", { task_name: "missing" });

    expect(result).toEqual({
      isError: true,
      content: [{ type: "text", text: JSON.stringify(problem) }],
    });
    expect(await metrics.registry.metrics()).toContain(
      'gradiated_mcp_tool_calls_total{tool="get_task",outcome="rejected",service="mcp"} 1',
    );
  });

  it("refuses a result too long for a model's context", async () => {
    const { app } = testApp({
      api: () =>
        Response.json({ data: [], padding: "x".repeat(MAX_RESULT_CHARACTERS) }),
    });

    const result = await callTool(app, "list_tasks");

    expect(result.isError).toBe(true);
    expect(result.content[0].text).toMatch(/over the 100000 limit/);
  });

  it("reports an unreachable API as a failed call", async () => {
    const { app, metrics } = testApp({
      api: (url) => {
        if (url.pathname.endsWith("/tasks"))
          throw new TypeError("fetch failed");

        return undefined;
      },
    });

    const result = await callTool(app, "list_tasks");

    expect(result).toEqual({
      isError: true,
      content: [{ type: "text", text: "The request could not be completed." }],
    });
    expect(await metrics.registry.metrics()).toContain(
      'gradiated_mcp_tool_calls_total{tool="list_tasks",outcome="failed",service="mcp"} 1',
    );
  });

  it.each([
    [{ name: "get_task", arguments: {} }, "Missing arguments: task_name."],
    [
      { name: "get_task", arguments: { task_name: "a", workspace_id: "b" } },
      "Unknown arguments: workspace_id.",
    ],
    [
      { name: "list_models", arguments: { external: "true" } },
      "Unknown arguments: external.",
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

describe("call_model", () => {
  const messages = [{ role: "user", content: "Hello" }];

  it("sends an API key's call to the gateway with that key, never streaming", async () => {
    const { app, fetchApi } = testApp();

    await callTool(app, "call_model", { model: "acme/support", messages });

    const [input, init] = fetchApi.mock.calls.at(-1)!;
    expect(String(input)).toBe("http://inference.internal/v1/chat/completions");
    expect(new Headers(init?.headers).get("authorization")).toBe(
      `Bearer ${apiKey}`,
    );
    expect(JSON.parse(String(init?.body))).toEqual({
      stream: false,
      model: "acme/support",
      messages,
    });
  });

  it("gives an OAuth connection an inference key, reuses it and renews a rejected one", async () => {
    let rejectNext = false;
    const { app, fetchApi, metrics } = testApp({
      inference: () => {
        if (!rejectNext) return Response.json({ id: "chatcmpl-1" });

        rejectNext = false;
        return Response.json({ error: "invalid_api_key" }, { status: 401 });
      },
    });
    const keysUsed = () =>
      fetchApi.mock.calls
        .filter(
          ([input]) => new URL(String(input)).host === "inference.internal",
        )
        .map(([, init]) => new Headers(init?.headers).get("authorization"));
    const call = () =>
      callTool(
        app,
        "call_model",
        { model: "acme/support", messages },
        oauthToken,
      );

    await call();
    await call();
    rejectNext = true;
    const renewed = await call();

    expect(renewed.isError).toBeUndefined();
    expect(keysUsed()).toEqual([
      `Bearer grad_${"1".repeat(43)}`,
      `Bearer grad_${"1".repeat(43)}`,
      `Bearer grad_${"1".repeat(43)}`,
      `Bearer grad_${"2".repeat(43)}`,
    ]);
    const exported = await metrics.registry.metrics();
    expect(exported).toContain(
      'gradiated_mcp_inference_credentials_total{result="minted",service="mcp"} 2',
    );
    expect(exported).toContain(
      'gradiated_mcp_inference_credentials_total{result="cached",service="mcp"} 2',
    );
  });
});

describe("prompts", () => {
  it("lists prompts and fills one in", async () => {
    const { app } = testApp();

    const { result: list } = await (await rpc(app, "prompts/list")).json();
    const { result } = await (
      await rpc(app, "prompts/get", {
        name: "review_task_version",
        arguments: { task_name: "support", version: "v2" },
      })
    ).json();

    expect(list.prompts.map(({ name }: { name: string }) => name)).toContain(
      "review_task_version",
    );
    expect(result.messages[0].content.text).toContain(
      "Review version v2 of the task support.",
    );
  });

  it("rejects a prompt without its required arguments", async () => {
    const { app } = testApp();

    const { error } = await (
      await rpc(app, "prompts/get", { name: "compare_task_versions" })
    ).json();

    expect(error.message).toContain(
      "Missing arguments: task_name, version_a, version_b.",
    );
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
  it("explains how to connect and lists the tools and prompts", async () => {
    const { app, metrics } = testApp();

    const page = await (await app.request("/")).text();

    expect(page).toContain("https://mcp.gradiated.com/mcp");
    expect(page).toContain("claude mcp add --transport http gradiated");
    expect(page).toContain("add a custom connector with this URL");
    expect(page).toContain("<code>read_task_version_file</code>");
    expect(page).toContain("<code>review_task_version</code>");
    expect(await metrics.registry.metrics()).toContain(
      'gradiated_mcp_http_requests_total{method="GET",route="/",status="200",service="mcp"} 1',
    );
  });
});
