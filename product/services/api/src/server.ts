import { serve } from "@hono/node-server";
import { parseEnvironment } from "@gradiated/config";
import {
  createClickHouseRuntimeClient,
  createControlDatabase,
  createCatalogBillingService,
  createDeploymentStatusService,
  createOrganizationService,
  createProfilingWriter,
  createUsageService,
  createValkeyServingProjector,
  createWorkspaceApiKeyService,
  parseClickHouseRuntimeEnvironment,
} from "@gradiated/control";
import { createApp } from "./app.js";
import { ApiMetrics, startApiMetricsServer } from "./metrics.js";
import { createAuthService, resolveAuthTrustedOrigins } from "./auth.js";
import {
  createResendMagicLinkSender,
  createResendOtpSender,
  createTestMagicLinkTransport,
  createTestOtpTransport,
} from "./auth-email.js";
import {
  createBillingPaymentsService,
  createStripeGateway,
  unavailableBillingPaymentsService,
} from "./billing/stripe.js";
import { createValkeyClient } from "@gradiated/valkey";
import { createProfilingIngestApp } from "./profiling-ingest.js";
import {
  createDeploymentStatusIngestApp,
  parseDeploymentStatusTokens,
} from "./deployment-status-ingest.js";
import { Hono } from "hono";

const environment = parseEnvironment(process.env);
const { database, pool } = createControlDatabase(environment.DATABASE_URL);
const clickhouse = createClickHouseRuntimeClient(
  parseClickHouseRuntimeEnvironment(process.env),
);
const valkey = createValkeyClient(environment);
valkey.on("error", (error) => console.error("Valkey client error", error));
await valkey.connect();
const servingProjector = createValkeyServingProjector(valkey);
const catalogBilling = createCatalogBillingService(database, servingProjector);
const organizations = createOrganizationService(database, servingProjector);
const testMagicLinks = environment.AUTH_TEST_MODE
  ? createTestMagicLinkTransport()
  : undefined;
const testOtpCodes = environment.AUTH_TEST_MODE
  ? createTestOtpTransport()
  : undefined;
const sendMagicLink =
  testMagicLinks?.send ??
  createResendMagicLinkSender({
    from: environment.AUTH_EMAIL_FROM!,
    apiKey: environment.RESEND_API_KEY!,
  });
const sendOtp =
  testOtpCodes?.send ??
  createResendOtpSender({
    from: environment.AUTH_EMAIL_FROM!,
    apiKey: environment.RESEND_API_KEY!,
  });
const trustedOrigins = resolveAuthTrustedOrigins(
  environment.TRUSTED_ORIGINS,
  environment.NODE_ENV,
);
const auth = createAuthService(database, {
  baseUrl: environment.BETTER_AUTH_URL,
  github:
    environment.GITHUB_CLIENT_ID && environment.GITHUB_CLIENT_SECRET
      ? {
          clientId: environment.GITHUB_CLIENT_ID,
          clientSecret: environment.GITHUB_CLIENT_SECRET,
        }
      : undefined,
  google:
    environment.GOOGLE_CLIENT_ID && environment.GOOGLE_CLIENT_SECRET
      ? {
          clientId: environment.GOOGLE_CLIENT_ID,
          clientSecret: environment.GOOGLE_CLIENT_SECRET,
        }
      : undefined,
  onUserCreated: async (user) => {
    await organizations.ensurePersonalForUser(user.id);
  },
  secret: environment.BETTER_AUTH_SECRET,
  sendMagicLink,
  sendOtp,
  takeTestMagicLink: testMagicLinks?.take,
  takeTestOtp: testOtpCodes?.take,
  trustedOrigins,
});
const metrics = new ApiMetrics();
const metricsPort = Number(process.env.METRICS_PORT ?? "9464");
const deploymentStatusTokens = parseDeploymentStatusTokens(
  process.env.DEPLOYMENT_STATUS_INGEST_TOKENS,
);
const app = createApp({
  allowedOrigins: trustedOrigins,
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
    usage: createUsageService(database, clickhouse),
    workspaces: createWorkspaceApiKeyService(database, servingProjector),
  },
});
if (deploymentStatusTokens.size > 0) {
  app.route(
    "/",
    createDeploymentStatusIngestApp({
      tokens: deploymentStatusTokens,
      service: createDeploymentStatusService(database, valkey),
    }),
  );
}

const server = serve({
  fetch: app.fetch,
  hostname: environment.HOST,
  port: environment.PORT,
});
const metricsServer = startApiMetricsServer(metrics, "0.0.0.0", metricsPort);
const profilingToken = process.env.PROFILING_INGEST_TOKEN;
const profilingClient = profilingToken
  ? createClickHouseRuntimeClient(
      parseClickHouseRuntimeEnvironment(process.env),
    )
  : undefined;
const privateApp = new Hono();
if (profilingToken) {
  privateApp.route(
    "/",
    createProfilingIngestApp({
      token: profilingToken,
      writer: createProfilingWriter(profilingClient!),
    }),
  );
}
const privateServer = profilingToken
  ? serve({
      fetch: privateApp.fetch,
      hostname:
        process.env.TELEMETRY_HOST ?? process.env.PROFILING_HOST ?? "0.0.0.0",
      port: Number(
        process.env.TELEMETRY_PORT ?? process.env.PROFILING_PORT ?? "3003",
      ),
    })
  : undefined;

console.log(
  `Gradiated API listening on http://${environment.HOST}:${environment.PORT}`,
);
console.log(
  `Gradiated API metrics listening on http://0.0.0.0:${metricsPort}/metrics`,
);
if (privateServer) {
  console.log(
    "Runtime telemetry ingestion listening on the private service port",
  );
}

const shutdown = (signal: NodeJS.Signals): void => {
  console.log(`Received ${signal}; shutting down`);
  metricsServer.close();
  privateServer?.close();
  server.close(async (error) => {
    if (error) {
      console.error("API shutdown failed", error);
      process.exitCode = 1;
    }
    if (valkey.isOpen) await valkey.quit();
    await profilingClient?.close();
    await clickhouse.close();
    await pool.end();
  });
};

process.once("SIGINT", shutdown);
process.once("SIGTERM", shutdown);
