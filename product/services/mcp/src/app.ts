import type { HttpBindings } from "@hono/node-server";
import { WebStandardStreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/webStandardStreamableHttp.js";
import { Hono, type Context } from "hono";
import { bodyLimit } from "hono/body-limit";
import { cors } from "hono/cors";

import type { ApiClient, Caller } from "./api-client.js";
import { renderIndexPage } from "./index-page.js";
import { createMcpServer } from "./server.js";
import type { ToolDefinition } from "./tools/definitions.js";

type Environment = { Bindings: Partial<HttpBindings> };

export interface AppOptions {
  api: ApiClient;
  tools: readonly ToolDefinition[];
  publicUrl: string;
  consoleUrl: string;
}

const API_KEY = /^grad_\S+$/;

const credential = (context: Context): string | undefined => {
  const bearer = context.req
    .header("authorization")
    ?.match(/^Bearer\s+(\S+)$/i)?.[1];
  const key = bearer ?? context.req.header("x-api-key");

  return key && API_KEY.test(key) ? key : undefined;
};

// The load balancer appends the address it saw after any client-supplied ones.
const clientAddress = (context: Context<Environment>) =>
  context.req.header("x-forwarded-for")?.split(",").at(-1)?.trim() ||
  context.env?.incoming?.socket?.remoteAddress;

const unauthorized = (context: Context, message: string) =>
  context.json(
    { jsonrpc: "2.0", error: { code: -32001, message }, id: null },
    401,
    { "WWW-Authenticate": 'Bearer realm="gradiated"' },
  );

export const createApp = ({
  api,
  tools,
  publicUrl,
  consoleUrl,
}: AppOptions) => {
  const app = new Hono<Environment>();
  const mcpUrl = new URL("/mcp", publicUrl).href;
  const indexPage = renderIndexPage({ mcpUrl, consoleUrl, tools });

  app.get("/", (context) => context.html(indexPage));
  app.get("/health/live", (context) => context.text("ok"));

  // Callers authenticate with a bearer key, never cookies, so any origin may call.
  app.use(
    "/mcp",
    cors({
      origin: "*",
      allowMethods: ["GET", "POST", "DELETE", "OPTIONS"],
      allowHeaders: [
        "Authorization",
        "Content-Type",
        "Mcp-Protocol-Version",
        "Mcp-Session-Id",
        "X-Api-Key",
      ],
      exposeHeaders: ["Mcp-Session-Id", "WWW-Authenticate"],
    }),
  );
  app.use("/mcp", bodyLimit({ maxSize: 1024 * 1024 }));

  app.all("/mcp", async (context) => {
    const key = credential(context);
    if (!key)
      return unauthorized(
        context,
        "Send a workspace API key as a bearer token.",
      );

    const caller: Caller = {
      authorization: `Bearer ${key}`,
      forwardedFor: clientAddress(context),
    };
    const principal = await api.authenticate(caller);
    if (!principal)
      return unauthorized(
        context,
        "The API key is unknown, expired or revoked.",
      );

    const server = createMcpServer(tools, api, principal);
    // Without a session ID generator the transport is stateless, one request at a time.
    const transport = new WebStandardStreamableHTTPServerTransport({
      enableJsonResponse: true,
    });

    try {
      await server.connect(transport);

      return await transport.handleRequest(context.req.raw);
    } finally {
      await server.close();
    }
  });

  return app;
};
