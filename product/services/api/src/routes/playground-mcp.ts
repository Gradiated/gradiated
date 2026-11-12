import {
  CallMcpToolSchema,
  ListMcpToolsSchema,
  McpToolListSchema,
  McpToolResultSchema,
  WorkspacePathSchema,
  problemContent,
} from "@gradiated/contracts";
import type { WorkspaceApiKeyService } from "@gradiated/control";
import { createRoute, type OpenAPIHono } from "@hono/zod-openapi";

import { consoleOnly } from "../http/audience.js";
import { ApiProblem, problems, requireUser } from "../http/problems.js";
import type { McpProxy } from "../mcp/proxy.js";
import type { ApiEnvironment } from "../types.js";

const errors = {
  401: { description: "Authentication is required.", content: problemContent },
  403: {
    description: "The playground is unavailable in this workspace.",
    content: problemContent,
  },
  404: { description: "The workspace was not found.", content: problemContent },
  422: {
    description: "The server URL or headers are invalid.",
    content: problemContent,
  },
  502: {
    description: "The MCP server could not be reached or failed.",
    content: problemContent,
  },
} as const;

const listMcpToolsRoute = createRoute({
  ...consoleOnly,
  method: "post",
  path: "/api/v1/workspaces/{workspace_id}/playground/mcp-tool-lists",
  operationId: "listPlaygroundMcpTools",
  summary: "List MCP server tools",
  description:
    "Connects to a remote MCP server for the playground and lists its tools. The connection's headers are used for this request only.",
  tags: ["Playground"],
  request: {
    params: WorkspacePathSchema,
    body: {
      required: true,
      content: { "application/json": { schema: ListMcpToolsSchema } },
    },
  },
  responses: {
    200: {
      description: "The server and its tools.",
      content: { "application/json": { schema: McpToolListSchema } },
    },
    ...errors,
  },
});

const callMcpToolRoute = createRoute({
  ...consoleOnly,
  method: "post",
  path: "/api/v1/workspaces/{workspace_id}/playground/mcp-tool-calls",
  operationId: "callPlaygroundMcpTool",
  summary: "Call MCP server tool",
  description:
    "Calls one tool on a remote MCP server for a playground model's tool call. A failed tool is a result with is_error, not an error response.",
  tags: ["Playground"],
  request: {
    params: WorkspacePathSchema,
    body: {
      required: true,
      content: { "application/json": { schema: CallMcpToolSchema } },
    },
  },
  responses: {
    200: {
      description: "The tool's result.",
      content: { "application/json": { schema: McpToolResultSchema } },
    },
    ...errors,
  },
});

export const registerPlaygroundMcpRoutes = (
  app: OpenAPIHono<ApiEnvironment>,
  workspaces: Pick<WorkspaceApiKeyService, "requirePlaygroundAccess">,
  proxy: McpProxy,
): void => {
  const relay = async <Result>(request: () => Promise<Result>) => {
    try {
      return await request();
    } catch (error) {
      throw new ApiProblem(
        problems.upstreamFailed(
          error instanceof Error ? error.message : "The MCP server failed.",
        ),
        error,
      );
    }
  };

  app.openapi(listMcpToolsRoute, async (context) => {
    const user = await requireUser(context);
    const { workspace_id } = context.req.valid("param");
    const { server } = context.req.valid("json");
    await workspaces.requirePlaygroundAccess(user.id, workspace_id);

    return context.json(await relay(() => proxy.listTools(server)), 200);
  });

  app.openapi(callMcpToolRoute, async (context) => {
    const user = await requireUser(context);
    const { workspace_id } = context.req.valid("param");
    const body = context.req.valid("json");
    await workspaces.requirePlaygroundAccess(user.id, workspace_id);

    return context.json(
      await relay(() => proxy.callTool(body.server, body.name, body.arguments)),
      200,
    );
  });
};
