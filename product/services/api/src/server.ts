import { createExternalModelCatalog } from "./catalog/external-models.js";
import { createPostHogServer } from "@gradiated/analytics/server";
import { createApiAnalytics, createSignupHandler } from "./analytics.js";
import { createEvaluationModelValidator } from "./catalog/evaluation-models.js";
import { createTrainingEngine } from "./training/engine.js";
import { serve } from "@hono/node-server";
import { createGpuControlApp } from "./gpu-control.js";
import {
  createCatalogBillingService,
  createClickHouseRuntimeClient,
  createControlDatabase,
  createContentStore,
  createTraceService,
  createTrainingService,
  createAdapterDownloads,
  createAdapterHostingService,
  ObjectStorage,
  createDeploymentStatusService,
  createOrganizationService,
  createProfilingWriter,
  createUsageService,
  createWaitlistService,
  createWorkspaceApiKeyService,
  createWorkspaceStore,
  parseClickHouseRuntimeEnvironment,
} from "@gradiated/control";
import { createValkeyClient } from "@gradiated/valkey";

import { createApp } from "./app.js";
import {
  createAuthService,
  resolveAuthTrustedOrigins,
} from "./auth/service.js";
import { createStripeGateway } from "./billing/stripe-gateway.js";
import {
  createBillingPaymentsService,
  unavailableBillingPaymentsService,
} from "./billing/top-ups.js";
import {
  createResendMagicLinkSender,
  createResendOtpSender,
  type MagicLinkMessage,
  type OtpCodeMessage,
} from "./email/auth-messages.js";
import { createTestMailbox } from "./email/test-mailbox.js";
import {
  createLoggingWaitlistWelcomeSender,
  createResendWaitlistWelcomeSender,
} from "./email/waitlist-welcome.js";
import { parseApiEnvironment } from "./environment.js";
import { createProfilingIngestApp } from "./ingest/profiling.js";
import { serviceLog } from "./logging.js";
import { ApiMetrics, startApiMetricsServer } from "./metrics.js";
import { createReadinessCheck } from "./readiness.js";

const environment = parseApiEnvironment(process.env);
const analyticsFailed = () => serviceLog("warn", "analytics_delivery_failed");
const posthog = createPostHogServer({
  key: environment.POSTHOG_KEY,
  host: environment.POSTHOG_HOST,
  onError: analyticsFailed,
});

// Keep the API within 100 database connections at its 20-pod ceiling.
const { database, pool } = createControlDatabase(environment.DATABASE_URL, 5);
const workspaceRecords = createWorkspaceStore(database);
const analytics = createApiAnalytics(
  posthog,
  async (id) => (await workspaceRecords.get(id))?.organizationId,
  analyticsFailed,
);

const clickhouse = createClickHouseRuntimeClient(
  parseClickHouseRuntimeEnvironment(process.env),
);
const valkey = createValkeyClient(environment);

valkey.on("error", (error) =>
  serviceLog("error", "dependency_error", { dependency: "valkey", error }),
);
await valkey.connect();

const catalogBilling = createCatalogBillingService(database);
const organizations = createOrganizationService(database);
const contents = createContentStore(
  environment.CONTENTS_BUCKET ?? "unconfigured",
);
const trustedOrigins = resolveAuthTrustedOrigins(
  environment.TRUSTED_ORIGINS,
  environment.NODE_ENV,
);

const createEmailSenders = () => {
  if (environment.authEmail.kind === "test") {
    const magicLinks = createTestMailbox();
    const otpCodes = createTestMailbox();

    return {
      sendMagicLink: async ({ email, url }: MagicLinkMessage) =>
        magicLinks.send(email, url),
      sendOtp: async ({ email, code }: OtpCodeMessage) =>
        otpCodes.send(email, code),
      sendWaitlistWelcome: createLoggingWaitlistWelcomeSender(),
      authTestMailbox: {
        takeMagicLink: magicLinks.take,
        takeOtp: otpCodes.take,
      },
    };
  }

  const resend = environment.authEmail;

  return {
    sendMagicLink: createResendMagicLinkSender(resend),
    sendOtp: createResendOtpSender(resend),
    sendWaitlistWelcome: createResendWaitlistWelcomeSender({
      ...resend,
      consoleUrl: environment.CONSOLE_URL,
    }),
  };
};

const { sendWaitlistWelcome, authTestMailbox, ...authEmail } =
  createEmailSenders();

const auth = createAuthService(database, {
  ...authEmail,
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
  onUserCreated: createSignupHandler(
    (id) => organizations.ensurePersonalForUser(id),
    posthog,
  ),
  onSessionCreated: async (session) => {
    posthog.track(
      session.userId,
      "user_signed_in",
      { user_id: session.userId, session_id: session.id },
      session.id,
    );
  },
  secret: environment.BETTER_AUTH_SECRET,
  trustedOrigins,
});
const metrics = new ApiMetrics();

const trainingEngine = createTrainingEngine(process.env);
const adapterDownloads = createAdapterDownloads(
  environment.TRAINING_ARTIFACTS_BUCKET
    ? new ObjectStorage(environment.TRAINING_ARTIFACTS_BUCKET)
    : undefined,
);

const externalModels = createExternalModelCatalog();
const validateEvaluationModel = createEvaluationModelValidator(
  externalModels,
  catalogBilling,
);

const app = createApp({
  analytics,
  externalModels,
  allowedOrigins: trustedOrigins,
  auth,
  authTestMailbox,
  checkDependencies: createReadinessCheck({ pool, valkey, timeoutMs: 2_000 }),
  metrics,
  sendWaitlistWelcome,
  services: {
    billingPayments:
      environment.STRIPE_SECRET_KEY && environment.STRIPE_WEBHOOK_SECRET
        ? createBillingPaymentsService({
            gateway: createStripeGateway({
              secretKey: environment.STRIPE_SECRET_KEY,
              webhookSecret: environment.STRIPE_WEBHOOK_SECRET,
            }),
            accounts: catalogBilling,
            productUrl: environment.CONSOLE_URL,
          })
        : unavailableBillingPaymentsService(),
    catalogBilling,
    organizations,
    usage: createUsageService(database, clickhouse),
    waitlist: createWaitlistService(database),
    workspaces: createWorkspaceApiKeyService(database, validateEvaluationModel),
    traces: createTraceService(database, contents),
    training: createTrainingService(
      database,
      contents,
      adapterDownloads,
      trainingEngine.engine,
      validateEvaluationModel,
    ),
  },
});

const server = serve({
  fetch: app.fetch,
  hostname: environment.HOST,
  port: environment.PORT,
  // Keep backend connections open beyond the public ALB's 660-second idle timeout.
  serverOptions: { keepAliveTimeout: 670_000 },
});
const runtimeBundleStorage = environment.TRAINING_ARTIFACTS_BUCKET
  ? new ObjectStorage(environment.TRAINING_ARTIFACTS_BUCKET)
  : undefined;
const gpuControlServer = environment.GPU_CONTROL_PROVIDER
  ? serve({
      fetch: createGpuControlApp({
        provider: environment.GPU_CONTROL_PROVIDER,
        status: createDeploymentStatusService(database, valkey),
        adapters: {
          service: createAdapterHostingService(database, adapterDownloads),
        },
        ...(runtimeBundleStorage
          ? {
              runtimeBundle: async (digest: string) => {
                const key = `bundles/sha256/${digest}.tar.gz`;
                if (!(await runtimeBundleStorage.exists(key))) return;
                return {
                  url: await runtimeBundleStorage.signDownload(key, {
                    expiresIn: 7200,
                  }),
                };
              },
            }
          : {}),
        check: createReadinessCheck({ pool, valkey, timeoutMs: 2_000 }),
      }).fetch,
      hostname: environment.HOST,
      port: environment.GPU_CONTROL_PORT,
    })
  : undefined;
const metricsServer = startApiMetricsServer(
  metrics,
  "0.0.0.0",
  environment.METRICS_PORT,
);
const profilingServer = environment.PROFILING_INGEST_TOKEN
  ? serve({
      fetch: createProfilingIngestApp({
        token: environment.PROFILING_INGEST_TOKEN,
        writer: createProfilingWriter(clickhouse),
      }).fetch,
      hostname: environment.PROFILING_HOST,
      port: environment.PROFILING_PORT,
    })
  : undefined;

serviceLog("info", "api_started");
if (profilingServer) serviceLog("info", "private_telemetry_started");

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
    serviceLog("error", "api_shutdown_failed", { dependency, error });
    process.exitCode = 1;
  }
};

const shutdown = async (signal: NodeJS.Signals) => {
  serviceLog("info", "api_stopping", { signal });

  await Promise.all([
    release("http", () => closeServer(server)),
    release("metrics", () => closeServer(metricsServer)),
    gpuControlServer
      ? release("gpu-control", () => closeServer(gpuControlServer))
      : undefined,
    profilingServer
      ? release("profiling", () => closeServer(profilingServer))
      : undefined,
  ]);

  await release("analytics", analytics.flush);
  await release("valkey", async () => {
    if (valkey.isOpen) await valkey.quit();
  });
  await release("clickhouse", () => clickhouse.close());
  await release("temporal", trainingEngine.close);
  await release("postgres", () => pool.end());
};

process.once("SIGINT", (signal) => void shutdown(signal));
process.once("SIGTERM", (signal) => void shutdown(signal));
