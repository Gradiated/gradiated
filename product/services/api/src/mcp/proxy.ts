import type {
  McpServerConnection,
  McpToolList,
  McpToolResult,
} from "@gradiated/contracts";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import type { Transport } from "@modelcontextprotocol/sdk/shared/transport.js";
import type { CallToolResult } from "@modelcontextprotocol/sdk/types.js";

const MAX_TOOLS = 200;
const MAX_TOOL_PAGES = 10;
const MAX_RESULT_CHARACTERS = 100_000;
const CALL_TIMEOUT_MS = 60_000;

export class McpServerError extends Error {}

export interface McpProxy {
  listTools(server: McpServerConnection): Promise<McpToolList>;
  callTool(
    server: McpServerConnection,
    name: string,
    input: Record<string, unknown>,
  ): Promise<McpToolResult>;
}

const resultText = (result: CallToolResult): string => {
  const text = result.content
    .map((block) => {
      switch (block.type) {
        case "text":
          return block.text;
        case "resource":
          return "text" in block.resource
            ? block.resource.text
            : `[Binary resource ${block.resource.uri}]`;
        case "resource_link":
          return `[Resource ${block.uri}]`;
        default:
          return `[${block.type} content omitted]`;
      }
    })
    .join("\n");
  const content =
    text ||
    (result.structuredContent ? JSON.stringify(result.structuredContent) : "");

  return content.length > MAX_RESULT_CHARACTERS
    ? `${content.slice(0, MAX_RESULT_CHARACTERS)}\n[Truncated after ${MAX_RESULT_CHARACTERS} characters.]`
    : content;
};

export const createMcpProxy = (outboundFetch: typeof fetch): McpProxy => {
  const connected = async <Result>(
    server: McpServerConnection,
    use: (client: Client) => Promise<Result>,
  ): Promise<Result> => {
    const client = new Client({ name: "gradiated-playground", version: "1" });
    const transport = new StreamableHTTPClientTransport(new URL(server.url), {
      fetch: outboundFetch,
      requestInit: { headers: server.headers },
    });

    try {
      // The SDK's transport type predates exactOptionalPropertyTypes.
      await client.connect(transport as Transport, {
        timeout: CALL_TIMEOUT_MS,
      });

      return await use(client);
    } catch (error) {
      throw new McpServerError(
        error instanceof Error ? error.message : "The MCP server failed.",
        { cause: error },
      );
    } finally {
      await client.close().catch(() => undefined);
    }
  };

  return {
    listTools: (server) =>
      connected(server, async (client) => {
        const tools: McpToolList["tools"] = [];
        let cursor: string | undefined;

        for (let page = 0; page < MAX_TOOL_PAGES; page++) {
          const result = await client.listTools(cursor ? { cursor } : {}, {
            timeout: CALL_TIMEOUT_MS,
          });
          for (const tool of result.tools)
            tools.push({
              name: tool.name,
              title: tool.title ?? tool.annotations?.title ?? null,
              description: tool.description ?? null,
              input_schema: tool.inputSchema,
              read_only: tool.annotations?.readOnlyHint === true,
            });

          cursor = result.nextCursor;
          if (!cursor || tools.length >= MAX_TOOLS) break;
        }

        const info = client.getServerVersion();

        return {
          server: {
            name: info?.name ?? new URL(server.url).hostname,
            version: info?.version ?? "",
            instructions: client.getInstructions() ?? null,
          },
          tools: tools.slice(0, MAX_TOOLS),
        };
      }),

    callTool: (server, name, input) =>
      connected(server, async (client) => {
        const result = (await client.callTool(
          { name, arguments: input },
          undefined,
          { timeout: CALL_TIMEOUT_MS },
        )) as CallToolResult;

        return { is_error: result.isError === true, text: resultText(result) };
      }),
  };
};
