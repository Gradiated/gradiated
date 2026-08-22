import { serve } from "@hono/node-server";
import { parseEnvironment } from "@gradiated/config";
import {
  createClickHouseRuntimeClient,
  createControlDatabase,
  createCatalogBillingService,
  createOrganizationService,
  createProfilingWriter,
  createValkeyServingProjector,
  createWorkspaceApiKeyService,
  parseClickHouseRuntimeEnvironment,
} from "@gradiated/control";
import { createApp } from "./app.js";
import { ApiMetrics, startApiMetricsServer } from "./metrics.js";
import { createAuthService } from "./auth.js";
import {
  createSesMagicLinkSender,
  createTestMagicLinkTransport,
} from "./auth-email.js";
import {
  createBillingPaymentsService,
  createStripeGateway,
  unavailableBillingPaymentsService,
} from "./billing/stripe.js";
import { createValkeyClient } from "@gradiated/valkey";
import { createProfilingIngestApp } from "./profiling-ingest.js";

const environment = parseEnvironment(process.env);
const { database, pool } = createControlDatabase(environment.DATABASE_URL);
const valkey = createValkeyClient(environment);
valkey.on("error", (error) => console.error("Valkey client error", error));
await valkey.connect();
const servingProjector = createValkeyServingProjector(valkey);
const catalogBilling = createCatalogBillingService(database, servingProjector);
const organizations = createOrganizationService(database, servingProjector);
const testMagicLinks = environment.AUTH_TEST_MODE
  ? createTestMagicLinkTransport()
  : undefined;
const sendMagicLink =
  testMagicLinks?.send ??
  createSesMagicLinkSender({
    from: environment.AUTH_EMAIL_FROM!,
    region: environment.SES_REGION!,
  });
const auth = createAuthService(database, {
  baseUrl: environment.BETTER_AUTH_URL,
  github:
    environment.GITHUB_CLIENT_ID && environment.GITHUB_CLIENT_SECRET
      ? {
          clientId: environment.GITHUB_CLIENT_ID,
          clientSecret: environment.GITHUB_CLIENT_SECRET,
        }
      : undefined,
  onUserCreated: async (user) => {
    await organizations.ensurePersonalForUser(user.id);
  },
  secret: environment.BETTER_AUTH_SECRET,
  sendMagicLink,
  takeTestMagicLink: testMagicLinks?.take,
  trustedOrigins: environment.TRUSTED_ORIGINS,
});
const metrics = new ApiMetrics();
const app = createApp({
  allowedOrigins: environment.TRUSTED_ORIGINS,
  auth,
  metrics,
  checkDependencies: async () => {
    const checks: Record<string, "up" | "down"> = {
      postgres: "down",
      valkey: "down",
    };
    await pool.query("select 1").then(
      () => (checks.postgres = "up"),
      () => undefined,
    );
    await valkey.ping().then(
      () => (checks.valkey = "up"),
      () => undefined,
    );
    return checks;
  },
  services: {
    billingPayments:
      environment.STRIPE_SECRET_KEY && environment.STRIPE_WEBHOOK_SECRET
        ? createBillingPaymentsService(
            createStripeGateway({
              secretKey: environment.STRIPE_SECRET_KEY,
              webhookSecret: environment.STRIPE_WEBHOOK_SECRET,
            }),
            catalogBilling,
            environment.CONSOLE_URL,
          )
        : unavailableBillingPaymentsService(),
    organizations,
    catalogBilling,
    workspaces: createWorkspaceApiKeyService(database, servingProjector),
  },
});

const server = serve({
  fetch: app.fetch,
  hostname: environment.HOST,
  port: environment.PORT,
});
const metricsServer = startApiMetricsServer(metrics);
const profilingToken = process.env.PROFILING_INGEST_TOKEN;
const profilingClient = profilingToken
  ? createClickHouseRuntimeClient(parseClickHouseRuntimeEnvironment(process.env))
  : undefined;
const profilingServer = profilingToken
  ? serve({
      fetch: createProfilingIngestApp({
        token: profilingToken,
        writer: createProfilingWriter(profilingClient!),
      }).fetch,
      hostname: process.env.PROFILING_HOST ?? "0.0.0.0",
      port: Number(process.env.PROFILING_PORT ?? "3003"),
    })
  : undefined;

console.log(
  `Gradiated API listening on http://${environment.HOST}:${environment.PORT}`,
);
console.log("Gradiated API metrics listening on http://0.0.0.0:9464/metrics");
if (profilingServer) {
  console.log("Profiling ingestion listening on the private service port");
}

const shutdown = (signal: NodeJS.Signals): void => {
  console.log(`Received ${signal}; shutting down`);
  metricsServer.close();
  profilingServer?.close();
  server.close(async (error) => {
    if (error) {
      console.error("API shutdown failed", error);
      process.exitCode = 1;
    }
    if (valkey.isOpen) await valkey.quit();
    await profilingClient?.close();
    await pool.end();
  });
};

process.once("SIGINT", shutdown);
process.once("SIGTERM", shutdown);
