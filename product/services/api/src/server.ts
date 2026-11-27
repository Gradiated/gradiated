import { createExternalModelCatalog } from "./catalog/external-models.js";
import { createPostHogServer } from "@gradiated/analytics/server";
import { createApiAnalytics, createSignupHandler } from "./analytics.js";
import { createEvaluationModelValidator } from "./catalog/evaluation-models.js";
import { MODEL_CATALOG } from "@gradiated/contracts/model-catalog";
import { createTrainingEngine } from "./training/engine.js";
import {
  createAdapterProbe,
  createQualificationLock,
  reportAdapterQualification,
} from "./training/adapter-probe.js";
import { serve } from "@hono/node-server";
import { createPandaDocNda, GRADIATED_NDA_TEMPLATE } from "./legal/pandadoc.js";
import {
  createSlackConnect,
  GRADIATED_ENGINEER_SLACK_USER_IDS,
} from "./slack/connect.js";
import { createGithubInstallations } from "./github/installations.js";
import { createGpuControlApp } from "./gpu-control.js";
import {
  createTopUpChargeStore,
  createStripeTopUpCharger,
  createStripeClient,
  createCatalogBillingService,
  createClickHouseRuntimeClient,
  createControlDatabase,
  createContentStore,
  createTraceService,
  createTrainingService,
  createAdapterDownloads,
  createGradArtifacts,
  ServingBasesSchema,
  createAdapterHostingService,
  createAdapterQualifier,
  createDeploymentStore,
  ObjectStorage,
  createDeploymentStatusService,
  createIntegrationService,
  createMemberService,
  createOrganizationService,
  createProfilingWriter,
  createTrainingBillingService,
  createUsageEventWriter,
  createUsageService,
  createWaitlistService,
  createWorkspaceApiKeyService,
  createWorkspaceStore,
  parseClickHouseRuntimeEnvironment,
} from "@gradiated/control";
import { createValkeyClient } from "@gradiated/valkey";

import { createApp } from "./app.js";
import { createOutboundFetch } from "./mcp/outbound.js";
import { createMcpProxy } from "./mcp/proxy.js";
import {
  createAuthService,
  resolveAuthTrustedOrigins,
} from "./auth/service.js";
import { createStripeGateway } from "./billing/stripe-gateway.js";
import {
  createBillingPaymentsService,
  unavailableBillingPaymentsService,
} from "./billing/payments.js";
import {
  createResendMagicLinkSender,
  createResendOtpSender,
  type MagicLinkMessage,
  type OtpCodeMessage,
} from "./email/auth-messages.js";
import {
  createResendInvitationSender,
  type InvitationMessage,
} from "./email/invitation.js";
import {
  createLoggingEngineerOnboardingNotifier,
  createResendEngineerOnboardingNotifier,
} from "./email/engineer-onboarding.js";
import { createTestMailbox } from "./email/test-mailbox.js";
import {
  createLoggingWaitlistWelcomeSender,
  createResendWaitlistWelcomeSender,
} from "./email/waitlist-welcome.js";
import { parseApiEnvironment } from "./environment.js";
import { createProfilingIngestApp } from "./ingest/profiling.js";
import { createTrainingInternalApp } from "./training-internal.js";
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
const stripe = environment.STRIPE_SECRET_KEY
  ? createStripeClient(environment.STRIPE_SECRET_KEY)
  : null;
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
    const invitationLinks = createTestMailbox();

    return {
      sendMagicLink: async ({ email, url }: MagicLinkMessage) =>
        magicLinks.send(email, url),
      sendOtp: async ({ email, code }: OtpCodeMessage) =>
        otpCodes.send(email, code),
      sendInvitation: async ({ email, url }: InvitationMessage) =>
        invitationLinks.send(email, url),
      sendWaitlistWelcome: createLoggingWaitlistWelcomeSender(),
      notifyEngineerOnboarding: createLoggingEngineerOnboardingNotifier(),
      authTestMailbox: {
        takeMagicLink: magicLinks.take,
        takeOtp: otpCodes.take,
        takeInvitation: invitationLinks.take,
      },
    };
  }

  const resend = environment.authEmail;

  return {
    sendMagicLink: createResendMagicLinkSender(resend),
    sendOtp: createResendOtpSender(resend),
    sendInvitation: createResendInvitationSender(resend),
    sendWaitlistWelcome: createResendWaitlistWelcomeSender({
      ...resend,
      consoleUrl: environment.CONSOLE_URL,
    }),
    notifyEngineerOnboarding: createResendEngineerOnboardingNotifier(resend),
  };
};

const {
  sendInvitation,
  sendWaitlistWelcome,
  notifyEngineerOnboarding,
  authTestMailbox,
  ...authEmail
} = createEmailSenders();

const auth = createAuthService(database, {
  ...authEmail,
  baseUrl: environment.BETTER_AUTH_URL,
  oauth: {
    consoleUrl: environment.CONSOLE_URL,
    mcpResource: environment.MCP_RESOURCE_URL,
  },
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
    (user) => organizations.ensureForNewUser(user),
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
metrics.initializeAdapterQualifications(
  MODEL_CATALOG.flatMap((model) =>
    "training" in model && model.training ? [model.id] : [],
  ),
);

const trainingEngine = createTrainingEngine(process.env);
const artifactStorage = environment.TRAINING_ARTIFACTS_BUCKET
  ? new ObjectStorage(environment.TRAINING_ARTIFACTS_BUCKET)
  : undefined;
const gradBundles = environment.GRAD_ARTIFACTS_BUCKET
  ? new ObjectStorage(environment.GRAD_ARTIFACTS_BUCKET)
  : undefined;
const grad = environment.GRAD_SERVER_URL
  ? createGradArtifacts({
      baseUrl: environment.GRAD_SERVER_URL,
      authorization: async ({ workspaceId, scopes }) =>
        (
          await auth.signServiceToken({
            service: "inference",
            workspaceId,
            scopes,
          })
        ).token,
    })
  : undefined;
const adapterDownloads = createAdapterDownloads(artifactStorage, gradBundles);

const deploymentStore = createDeploymentStore(database);
const qualifyAdapter = createAdapterQualifier({
  targets: (modelId) => deploymentStore.adapterProbeTargets(modelId),
  probe: createAdapterProbe(),
  report: reportAdapterQualification(metrics),
});

const externalModels = createExternalModelCatalog();
const validateEvaluationModel = createEvaluationModelValidator(
  externalModels,
  catalogBilling,
);

const training = createTrainingService(
  database,
  contents,
  adapterDownloads,
  trainingEngine.engine,
  validateEvaluationModel,
  artifactStorage,
  qualifyAdapter,
  createQualificationLock(valkey),
  // Rotating this key invalidates every public report link.
  environment.BETTER_AUTH_SECRET,
  {
    ...(grad ? { grad } : {}),
    ...(gradBundles ? { bundles: gradBundles } : {}),
    ...(environment.GRAD_SERVING_BASES
      ? {
          servingBases: ServingBasesSchema.parse(
            JSON.parse(environment.GRAD_SERVING_BASES),
          ),
        }
      : {}),
  },
);
// One sweep at a time: while grad is down, each call waits out its timeout.
let releasingPins = false;
const pinReleases = grad
  ? setInterval(() => {
      if (releasingPins) return;
      releasingPins = true;
      training.artifacts
        .releasePendingPins()
        .catch((error: unknown) => {
          serviceLog("warn", "grad_pin_release_failed", { error });
        })
        .finally(() => {
          releasingPins = false;
        });
    }, 60_000).unref()
  : undefined;

const app = createApp({
  githubInstallations:
    environment.GITHUB_CLIENT_ID && environment.GITHUB_CLIENT_SECRET
      ? createGithubInstallations(environment.GITHUB_APP_SLUG)
      : undefined,
  slackConnect: environment.SLACK_BOT_TOKEN
    ? createSlackConnect({
        token: environment.SLACK_BOT_TOKEN,
        engineerUserIds: GRADIATED_ENGINEER_SLACK_USER_IDS,
      })
    : undefined,
  ndaDocuments: environment.PANDADOC_API_KEY
    ? createPandaDocNda({
        apiKey: environment.PANDADOC_API_KEY,
        ...GRADIATED_NDA_TEMPLATE,
      })
    : undefined,
  analytics,
  externalModels,
  mcpProxy: createMcpProxy(
    createOutboundFetch({
      allowPrivateNetworks: environment.MCP_PROXY_ALLOW_PRIVATE_NETWORKS,
    }),
  ),
  allowedOrigins: trustedOrigins,
  auth,
  authTestMailbox,
  checkDependencies: createReadinessCheck({ pool, valkey, timeoutMs: 2_000 }),
  consoleUrl: environment.CONSOLE_URL,
  metrics,
  sendInvitation,
  sendWaitlistWelcome,
  notifyEngineerOnboarding,
  services: {
    billingPayments:
      stripe && environment.STRIPE_WEBHOOK_SECRET
        ? createBillingPaymentsService({
            gateway: createStripeGateway({
              stripe,
              webhookSecret: environment.STRIPE_WEBHOOK_SECRET,
            }),
            accounts: catalogBilling,
            topUpCharges: createTopUpChargeStore(database),
            charger: createStripeTopUpCharger(stripe),
            productUrl: environment.CONSOLE_URL,
            publishableKey: environment.STRIPE_PUBLISHABLE_KEY,
            cardDetails: valkey,
          })
        : unavailableBillingPaymentsService(),
    catalogBilling,
    members: createMemberService(database),
    integrations: createIntegrationService(database),
    organizations,
    usage: createUsageService(database, clickhouse),
    waitlist: createWaitlistService(database),
    workspaces: createWorkspaceApiKeyService(database, validateEvaluationModel),
    traces: createTraceService(database, contents),
    training,
  },
});

const server = serve({
  fetch: app.fetch,
  hostname: environment.HOST,
  port: environment.PORT,
  // Keep backend connections open beyond the public ALB's 660-second idle timeout.
  serverOptions: { keepAliveTimeout: 670_000 },
});
const gpuControlServer = environment.GPU_CONTROL_PROVIDERS
  ? serve({
      fetch: createGpuControlApp({
        providers: environment.GPU_CONTROL_PROVIDERS,
        status: createDeploymentStatusService(database, valkey),
        adapters: {
          service: createAdapterHostingService(database, adapterDownloads),
        },
        ...(artifactStorage
          ? {
              runtimeBundle: async (digest: string) => {
                const key = `bundles/sha256/${digest}.tar.gz`;
                if (!(await artifactStorage.exists(key))) return;
                return {
                  url: await artifactStorage.signDownload(key, {
                    expiresIn: 7200,
                  }),
                };
              },
            }
          : {}),
        check: createReadinessCheck({ pool, valkey, timeoutMs: 2_000 }),
      }).fetch,
      hostname: environment.GPU_CONTROL_HOST,
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

const trainingInternalServer = environment.TRAINING_INTERNAL_TOKEN
  ? serve({
      fetch: createTrainingInternalApp({
        tokens: [
          environment.TRAINING_INTERNAL_TOKEN,
          ...(environment.TRAINING_INTERNAL_TOKEN_PREVIOUS
            ? [environment.TRAINING_INTERNAL_TOKEN_PREVIOUS]
            : []),
        ],
        billing: createTrainingBillingService(
          database,
          createUsageEventWriter(clickhouse),
        ),
      }).fetch,
      hostname: environment.TRAINING_INTERNAL_HOST,
      port: environment.TRAINING_INTERNAL_PORT,
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
  clearInterval(pinReleases);

  await Promise.all([
    release("http", () => closeServer(server)),
    release("metrics", () => closeServer(metricsServer)),
    gpuControlServer
      ? release("gpu-control", () => closeServer(gpuControlServer))
      : undefined,
    profilingServer
      ? release("profiling", () => closeServer(profilingServer))
      : undefined,
    trainingInternalServer
      ? release("training-internal", () => closeServer(trainingInternalServer))
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
