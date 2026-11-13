import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import {
  CallToolRequestSchema,
  ErrorCode,
  GetPromptRequestSchema,
  ListPromptsRequestSchema,
  ListToolsRequestSchema,
  McpError,
} from "@modelcontextprotocol/sdk/types.js";

import type { ApiClient, Principal } from "./api-client.js";
import type { Credentials } from "./credentials.js";
import type { McpMetrics } from "./metrics.js";
import { PROMPTS } from "./prompts.js";
import type { ToolDefinition } from "./tools/definitions.js";

export const SERVER_INFO = { name: "gradiated", version: "0.2.0" };

const INSTRUCTIONS =
  "Tools for one Gradiated workspace: models, usage, generations, tasks, their trained versions and those versions' reports and files, and calling models. The workspace comes from the credential; tools never take a workspace ID. Tasks, versions and files are named by their names.";

export interface ServerContext {
  tools: readonly ToolDefinition[];
  api: ApiClient;
  credentials: Credentials;
  metrics?: McpMetrics;
}

export const createMcpServer = (
  { tools, api, credentials, metrics }: ServerContext,
  principal: Principal,
): Server => {
  const server = new Server(SERVER_INFO, {
    capabilities: { tools: {}, prompts: {} },
    instructions: INSTRUCTIONS,
  });

  server.setRequestHandler(ListToolsRequestSchema, () => ({
    tools: tools.map(
      ({
        name,
        title,
        description,
        inputSchema,
        outputSchema,
        annotations,
      }) => ({
        name,
        title,
        description,
        inputSchema,
        ...(outputSchema ? { outputSchema } : {}),
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

    const started = process.hrtime.bigint();
    const { result, outcome } = await api.call(
      principal,
      tool,
      params.arguments ?? {},
      credentials.inferenceAuthorization(principal),
    );
    metrics?.toolCall(
      tool.name,
      outcome,
      Number(process.hrtime.bigint() - started) / 1e9,
    );

    return result;
  });

  server.setRequestHandler(ListPromptsRequestSchema, () => ({
    prompts: PROMPTS.map(({ name, title, description, arguments: args }) => ({
      name,
      title,
      description,
      arguments: args,
    })),
  }));

  server.setRequestHandler(GetPromptRequestSchema, ({ params }) => {
    const prompt = PROMPTS.find(({ name }) => name === params.name);
    if (!prompt)
      throw new McpError(
        ErrorCode.InvalidParams,
        `Unknown prompt ${params.name}.`,
      );

    const values = params.arguments ?? {};
    const missing = prompt.arguments
      .filter(({ name, required }) => required && !values[name]?.trim())
      .map(({ name }) => name);
    if (missing.length)
      throw new McpError(
        ErrorCode.InvalidParams,
        `Missing arguments: ${missing.join(", ")}.`,
      );

    return {
      description: prompt.description,
      messages: [
        {
          role: "user",
          content: { type: "text", text: prompt.text(values) },
        },
      ],
    };
  });

  return server;
};
