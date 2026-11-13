import { serve } from "@hono/node-server";

import { createApiClient } from "./api-client.js";
import { createApp } from "./app.js";
import { parseMcpEnvironment } from "./environment.js";
import { loadApiDocument } from "./openapi.js";
import { buildTools } from "./tools/definitions.js";

const environment = parseMcpEnvironment();
const app = createApp({
  api: createApiClient(environment.GRADIATED_API_URL),
  tools: buildTools(loadApiDocument()),
  publicUrl: environment.MCP_PUBLIC_URL,
  consoleUrl: environment.CONSOLE_URL,
});

const server = serve({
  fetch: app.fetch,
  hostname: environment.HOST,
  port: environment.PORT,
});

const shutdown = () => server.close(() => process.exit(0));
process.once("SIGTERM", shutdown);
process.once("SIGINT", shutdown);
