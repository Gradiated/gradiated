import { serve } from "@hono/node-server";
import { createValkeyClient } from "@gradiated/valkey";

import { createApiClient } from "./api-client.js";
import { createApp } from "./app.js";
import { createCredentialCache, type CacheStore } from "./cache.js";
import { createCredentials } from "./credentials.js";
import { parseMcpEnvironment } from "./environment.js";
import { createMcpMetrics, startMetricsServer } from "./metrics.js";
import { loadApiDocument } from "./openapi.js";
import { buildTools } from "./tools/definitions.js";

const environment = parseMcpEnvironment();
const metrics = createMcpMetrics();

const valkeyStore = (url: string): CacheStore => {
  const client = createValkeyClient({ ...environment, VALKEY_URL: url });

  metrics.dependency("valkey", false);
  client.on("ready", () => metrics.dependency("valkey", true));
  client.on("end", () => metrics.dependency("valkey", false));
  client.on("error", () => metrics.dependency("valkey", client.isReady));
  // The client reconnects on its own; requests skip the cache until it is ready.
  void client.connect().catch(() => undefined);

  const ready = () => {
    if (!client.isReady) throw new Error("Valkey is not connected.");

    return client;
  };

  return {
    get: async (key) => ready().get(key),
    set: async (key, value, ttlSeconds) => {
      await ready().set(key, value, { EX: ttlSeconds });
    },
    delete: async (key) => {
      await ready().del(key);
    },
  };
};

const api = createApiClient(
  environment.GRADIATED_API_URL,
  environment.GRADIATED_INFERENCE_URL,
);
const cache = createCredentialCache(
  environment.VALKEY_URL ? valkeyStore(environment.VALKEY_URL) : undefined,
  metrics.cache,
);
const app = createApp({
  api,
  tools: buildTools(loadApiDocument()),
  credentials: createCredentials(api, cache, metrics),
  metrics,
  publicUrl: environment.MCP_PUBLIC_URL,
  consoleUrl: environment.CONSOLE_URL,
  authorizationServer: environment.AUTHORIZATION_SERVER_URL,
});

const server = serve({
  fetch: app.fetch,
  hostname: environment.HOST,
  port: environment.PORT,
});
const metricsServer = startMetricsServer(
  metrics,
  environment.HOST,
  environment.METRICS_PORT,
);

const shutdown = () => {
  metricsServer.close();
  server.close(() => process.exit(0));
};
process.once("SIGTERM", shutdown);
process.once("SIGINT", shutdown);
