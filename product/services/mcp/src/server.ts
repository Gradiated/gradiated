import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";

import type { ApiClient, Principal } from "./api-client.js";
import type { ToolDefinition } from "./tools/definitions.js";

export const SERVER_INFO = { name: "gradiated", version: "0.1.0" };

const INSTRUCTIONS =
  "Tools for one Gradiated workspace: models, usage, generations, tasks, task versions and training runs. The workspace comes from the credential; tools never take a workspace ID.";

export const createMcpServer = (
  tools: readonly ToolDefinition[],
  api: ApiClient,
  principal: Principal,
): Server => {
  const server = new Server(SERVER_INFO, {
    capabilities: { tools: {} },
    instructions: INSTRUCTIONS,
  });

  server.setRequestHandler(ListToolsRequestSchema, () => ({
    tools: tools.map(
      ({ name, title, description, inputSchema, annotations }) => ({
        name,
        title,
        description,
        inputSchema,
        annotations,
      }),
    ),
  }));

  server.setRequestHandler(CallToolRequestSchema, async ({ params }) => {
    const tool = tools.find(({ name }) => name === params.name);
    if (!tool)
      return {
        isError: true,
        content: [{ type: "text", text: `Unknown tool ${params.name}.` }],
      };

    return api.call(principal, tool, params.arguments ?? {});
  });

  return server;
};
