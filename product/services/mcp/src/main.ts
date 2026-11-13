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

const valkey = environment.VALKEY_URL
  ? createValkeyClient({ ...environment, VALKEY_URL: environment.VALKEY_URL })
  : undefined;

const valkeyStore = (client: NonNullable<typeof valkey>): CacheStore => {
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
  valkey ? valkeyStore(valkey) : undefined,
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
  serverOptions: {
    // Beyond the ALB's 660 s idle timeout, so the ALB never reuses a connection Node closed.
    keepAliveTimeout: 670_000,
    // Node's 300 s default would cut off a call_model at its own 300 s limit.
    requestTimeout: 340_000,
  },
});
const metricsServer = startMetricsServer(
  metrics,
  environment.HOST,
  environment.METRICS_PORT,
);

const closeServer = (closable: {
  close(callback: (error?: Error) => void): unknown;
}) =>
  new Promise<void>((resolve, reject) => {
    closable.close((error) => (error ? reject(error) : resolve()));
  });

const release = async (dependency: string, close: () => Promise<unknown>) => {
  try {
    await close();
  } catch (error) {
    console.error(`MCP could not close ${dependency}.`, error);
    process.exitCode = 1;
  }
};

// The pod's preStop has already taken it out of the load balancer; open requests finish first.
const shutdown = async () => {
  await Promise.all([
    release("http", () => closeServer(server)),
    release("metrics", () => closeServer(metricsServer)),
  ]);
  await release("valkey", async () => {
    if (valkey?.isOpen) await valkey.quit();
  });
};
process.once("SIGTERM", () => void shutdown());
process.once("SIGINT", () => void shutdown());
