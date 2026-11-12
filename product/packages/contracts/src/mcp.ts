import { z } from "@hono/zod-openapi";

const HeaderNameSchema = z
  .string()
  .regex(/^[A-Za-z0-9!#$%&'*+.^_`|~-]{1,100}$/)
  .refine(
    (name) =>
      ![
        "host",
        "content-length",
        "content-type",
        "accept",
        "connection",
        "cookie",
      ].includes(name.toLowerCase()),
    "The proxy sets this header itself.",
  );

export const McpServerConnectionSchema = z
  .strictObject({
    url: z
      .url({ protocol: /^https?$/ })
      .max(2048)
      .describe("Streamable HTTP endpoint of a remote MCP server."),
    headers: z
      .record(HeaderNameSchema, z.string().max(8192))
      .refine(
        (headers) => Object.keys(headers).length <= 10,
        "At most 10 headers.",
      )
      .default({})
      .describe(
        "Headers sent to the server on every request, such as Authorization. They are not stored.",
      ),
  })
  .openapi("McpServerConnection");

export type McpServerConnection = z.infer<typeof McpServerConnectionSchema>;

export const McpToolSchema = z
  .object({
    name: z.string(),
    title: z.string().nullable(),
    description: z.string().nullable(),
    input_schema: z.record(z.string(), z.unknown()),
    read_only: z
      .boolean()
      .describe("Whether the server marks the tool read-only."),
  })
  .openapi("McpTool");

export type McpTool = z.infer<typeof McpToolSchema>;

export const ListMcpToolsSchema = z
  .strictObject({ server: McpServerConnectionSchema })
  .openapi("ListMcpTools");

export const McpToolListSchema = z
  .object({
    server: z.object({
      name: z.string(),
      version: z.string(),
      instructions: z.string().nullable(),
    }),
    tools: z.array(McpToolSchema),
  })
  .openapi("McpToolList");

export type McpToolList = z.infer<typeof McpToolListSchema>;

export const CallMcpToolSchema = z
  .strictObject({
    server: McpServerConnectionSchema,
    name: z.string().min(1).max(256),
    arguments: z.record(z.string(), z.unknown()).default({}),
  })
  .openapi("CallMcpTool");

export const McpToolResultSchema = z
  .object({
    is_error: z.boolean(),
    text: z
      .string()
      .describe(
        "The result's text content; other content types are summarized.",
      ),
  })
  .openapi("McpToolResult");

export type McpToolResult = z.infer<typeof McpToolResultSchema>;
