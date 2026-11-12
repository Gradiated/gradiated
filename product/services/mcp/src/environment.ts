import { z } from "zod";

const EnvironmentSchema = z.object({
  HOST: z.string().min(1).default("127.0.0.1"),
  PORT: z.coerce.number().int().min(1).max(65_535).default(3_007),
  // Where this service reaches the API; in production, the in-cluster service.
  GRADIATED_API_URL: z.url().default("http://127.0.0.1:3001"),
  MCP_PUBLIC_URL: z.url().default("https://mcp.gradiated.com"),
  CONSOLE_URL: z.url().default("https://console.gradiated.com"),
  // The OAuth issuer; RFC 8414 metadata is served on its origin.
  AUTHORIZATION_SERVER_URL: z
    .url()
    .default("https://api.gradiated.com/api/auth"),
});

export type McpEnvironment = z.infer<typeof EnvironmentSchema>;

export const parseMcpEnvironment = (
  environment: NodeJS.ProcessEnv = process.env,
): McpEnvironment => EnvironmentSchema.parse(environment);
