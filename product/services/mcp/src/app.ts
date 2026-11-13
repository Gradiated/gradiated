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
  authorizationServer: string;
}

const SCOPES = ["mcp", "offline_access"];

// A workspace API key or an OAuth access token from the API's authorization server.
const CREDENTIAL = /^grado?_\S+$/;

const credential = (context: Context): string | undefined => {
  const bearer = context.req
    .header("authorization")
    ?.match(/^Bearer\s+(\S+)$/i)?.[1];
  const key = bearer ?? context.req.header("x-api-key");

  return key && CREDENTIAL.test(key) ? key : undefined;
};

// The load balancer appends the address it saw after any client-supplied ones.
const clientAddress = (context: Context<Environment>) =>
  context.req.header("x-forwarded-for")?.split(",").at(-1)?.trim() ||
  context.env?.incoming?.socket?.remoteAddress;

const unauthorized = (
  context: Context,
  resourceMetadata: string,
  message: string,
) =>
  context.json(
    { jsonrpc: "2.0", error: { code: -32001, message }, id: null },
    401,
    {
      "WWW-Authenticate": `Bearer resource_metadata="${resourceMetadata}", scope="${SCOPES.join(" ")}"`,
    },
  );

export const createApp = ({
  api,
  tools,
  publicUrl,
  consoleUrl,
  authorizationServer,
}: AppOptions) => {
  const app = new Hono<Environment>();
  const mcpUrl = new URL("/mcp", publicUrl).href;
  const resourceMetadataUrl = new URL(
    "/.well-known/oauth-protected-resource/mcp",
    publicUrl,
  ).href;
  const indexPage = renderIndexPage({ mcpUrl, consoleUrl, tools });
  const resourceMetadata = {
    resource: mcpUrl,
    resource_name: "Gradiated",
    resource_documentation: new URL("/", publicUrl).href,
    authorization_servers: [authorizationServer],
    scopes_supported: SCOPES,
    bearer_methods_supported: ["header"],
  };

  app.get("/", (context) => context.html(indexPage));
  app.get("/health/live", (context) => context.text("ok"));

  // RFC 9728 metadata, at the path-suffixed location and the root one clients also try.
  app.use("/.well-known/*", cors({ origin: "*", allowMethods: ["GET"] }));
  for (const path of [
    "/.well-known/oauth-protected-resource/mcp",
    "/.well-known/oauth-protected-resource",
  ])
    app.get(path, (context) => context.json(resourceMetadata));

  // Callers authenticate with a bearer credential, never cookies, so any origin may call.
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
        resourceMetadataUrl,
        "Sign in with OAuth or send a workspace API key as a bearer token.",
      );

    const caller: Caller = {
      authorization: `Bearer ${key}`,
      forwardedFor: clientAddress(context),
    };
    const principal = await api.authenticate(caller);
    if (!principal)
      return unauthorized(
        context,
        resourceMetadataUrl,
        "The credential is unknown, expired or revoked.",
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
