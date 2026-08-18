import { serve } from "@hono/node-server";
import { parseEnvironment } from "@gradiated/config";
import {
  createControlDatabase,
  createCatalogBillingService,
  createOrganizationService,
  createValkeyServingProjector,
  createWorkspaceApiKeyService,
} from "@gradiated/control";
import { createApp } from "./app.js";
import { createAuthService } from "./auth.js";
import {
  createBillingPaymentsService,
  createStripeGateway,
  unavailableBillingPaymentsService,
} from "./billing/stripe.js";
import { createValkeyClient } from "./valkey.js";

const environment = parseEnvironment(process.env);
const { database, pool } = createControlDatabase(environment.DATABASE_URL);
const valkey = createValkeyClient(environment);
valkey.on("error", (error) => console.error("Valkey client error", error));
await valkey.connect();
const servingProjector = createValkeyServingProjector(valkey);
const catalogBilling = createCatalogBillingService(database, servingProjector);
const auth = createAuthService(database, {
  baseUrl: environment.BETTER_AUTH_URL,
  minPasswordLength: environment.BETTER_AUTH_MIN_PASSWORD_LENGTH,
  secret: environment.BETTER_AUTH_SECRET,
  trustedOrigins: environment.TRUSTED_ORIGINS,
});
const app = createApp({
  allowedOrigins: environment.TRUSTED_ORIGINS,
  auth,
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
    organizations: createOrganizationService(database, servingProjector),
    catalogBilling,
    workspaces: createWorkspaceApiKeyService(database, servingProjector),
  },
});

const server = serve({
  fetch: app.fetch,
  hostname: environment.HOST,
  port: environment.PORT,
});

console.log(
  `Gradiated API listening on http://${environment.HOST}:${environment.PORT}`,
);

const shutdown = (signal: NodeJS.Signals): void => {
  console.log(`Received ${signal}; shutting down`);
  server.close(async (error) => {
    if (error) {
      console.error("API shutdown failed", error);
      process.exitCode = 1;
    }
    if (valkey.isOpen) await valkey.quit();
    await pool.end();
  });
};

process.once("SIGINT", shutdown);
process.once("SIGTERM", shutdown);
