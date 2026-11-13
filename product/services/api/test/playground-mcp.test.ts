import type { AddressInfo } from "node:net";

import { ControlServiceError } from "@gradiated/control";
import { serve, type ServerType } from "@hono/node-server";
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { WebStandardStreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/webStandardStreamableHttp.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { Hono } from "hono";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";

import { createOutboundFetch } from "../src/mcp/outbound.js";
import { createMcpProxy } from "../src/mcp/proxy.js";
import {
  anonymous,
  authenticated,
  createTestApp,
  failWith,
  postJson,
  workspaceId,
} from "./support.js";

const TOKEN = "Bearer remote-token";
const toolListPath = `/api/v1/workspaces/${workspaceId}/playground/mcp-tool-lists`;
const toolCallPath = `/api/v1/workspaces/${workspaceId}/playground/mcp-tool-calls`;

const remoteServer = () => {
  const server = new Server(
    { name: "weather", version: "2.0.0" },
    { capabilities: { tools: {} }, instructions: "Ask about weather." },
  );
  server.setRequestHandler(ListToolsRequestSchema, () => ({
    tools: [
      {
        name: "forecast",
        description: "Gets a forecast.",
        inputSchema: {
          type: "object",
          properties: { city: { type: "string" } },
          required: ["city"],
        },
        annotations: { readOnlyHint: true },
      },
    ],
  }));
  server.setRequestHandler(CallToolRequestSchema, ({ params }) =>
    params.arguments?.city === "Atlantis"
      ? { isError: true, content: [{ type: "text", text: "Unknown city." }] }
      : {
          content: [
            {
              type: "text",
              text: `Sunny in ${String(params.arguments?.city)}.`,
            },
            { type: "image", data: "", mimeType: "image/png" },
          ],
        },
  );

  return server;
};

describe("playground MCP proxy", () => {
  let remote: ServerType;
  let url: string;

  beforeAll(async () => {
    const app = new Hono();
    app.all("/mcp", async (context) => {
      if (context.req.header("authorization") !== TOKEN)
        return context.text("unauthorized", 401);

      const server = remoteServer();
      const transport = new WebStandardStreamableHTTPServerTransport({
        enableJsonResponse: true,
      });
      await server.connect(transport);

      return transport.handleRequest(context.req.raw);
    });
    remote = await new Promise<ServerType>((resolve) => {
      const server = serve(
        { fetch: app.fetch, hostname: "127.0.0.1", port: 0 },
        () => resolve(server),
      );
    });
    url = `http://127.0.0.1:${(remote.address() as AddressInfo).port}/mcp`;
  });

  afterAll(() => new Promise<void>((resolve) => remote.close(() => resolve())));

  const testApp = (
    requirePlaygroundAccess = vi.fn(async () => undefined),
    auth = authenticated,
  ) => ({
    requirePlaygroundAccess,
    app: createTestApp({
      auth,
      mcpProxy: createMcpProxy(
        createOutboundFetch({ allowPrivateNetworks: true }),
      ),
      services: { workspaces: { requirePlaygroundAccess } },
    }),
  });

  const server = () => ({ url, headers: { Authorization: TOKEN } });

  it("lists a remote server's tools with the given headers", async () => {
    const { app, requirePlaygroundAccess } = testApp();

    const response = await postJson(app, toolListPath, { server: server() });

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({
      server: {
        name: "weather",
        version: "2.0.0",
        instructions: "Ask about weather.",
      },
      tools: [
        {
          name: "forecast",
          title: null,
          description: "Gets a forecast.",
          input_schema: {
            type: "object",
            properties: { city: { type: "string" } },
            required: ["city"],
          },
          read_only: true,
        },
      ],
    });
    expect(requirePlaygroundAccess).toHaveBeenCalledWith(
      expect.any(String),
      workspaceId,
    );
  });

  it("calls a tool and summarizes content that is not text", async () => {
    const { app } = testApp();

    const response = await postJson(app, toolCallPath, {
      server: server(),
      name: "forecast",
      arguments: { city: "Lisbon" },
    });

    expect(await response.json()).toEqual({
      is_error: false,
      text: "Sunny in Lisbon.\n[image content omitted]",
    });
  });

  it("returns a failed tool as a result", async () => {
    const { app } = testApp();

    const response = await postJson(app, toolCallPath, {
      server: server(),
      name: "forecast",
      arguments: { city: "Atlantis" },
    });

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({
      is_error: true,
      text: "Unknown city.",
    });
  });

  it("reports a server that rejects the headers as an upstream failure", async () => {
    const { app } = testApp();

    const response = await postJson(app, toolListPath, {
      server: { url, headers: { Authorization: "Bearer wrong" } },
    });

    expect(response.status).toBe(502);
    expect((await response.json()).code).toBe("upstream_failed");
  });

  it("refuses private addresses by default", async () => {
    const app = createTestApp({
      auth: authenticated,
      services: {
        workspaces: { requirePlaygroundAccess: async () => undefined },
      },
    });

    const response = await postJson(app, toolListPath, { server: server() });

    expect(response.status).toBe(502);
    expect((await response.json()).detail).toBe("MCP servers must use HTTPS.");
  });

  it("requires a session and playground access before connecting", async () => {
    const connect = vi.fn();
    const proxy = { listTools: connect, callTool: connect };

    const signedOut = createTestApp({ auth: anonymous, mcpProxy: proxy });
    expect(
      (await postJson(signedOut, toolListPath, { server: server() })).status,
    ).toBe(401);

    const archived = createTestApp({
      auth: authenticated,
      mcpProxy: proxy,
      services: {
        workspaces: {
          requirePlaygroundAccess: failWith(
            new ControlServiceError("forbidden", "Archived."),
          ),
        },
      },
    });
    expect(
      (await postJson(archived, toolListPath, { server: server() })).status,
    ).toBe(403);
    expect(connect).not.toHaveBeenCalled();
  });

  it.each([
    { url: "ftp://example.com/mcp" },
    { url: "https://example.com/mcp", headers: { Host: "internal" } },
    { url: "https://example.com/mcp", headers: { "bad header": "x" } },
  ])("rejects connection %#", async (connection) => {
    const { app } = testApp();

    expect(
      (await postJson(app, toolListPath, { server: connection })).status,
    ).toBe(422);
  });
});
