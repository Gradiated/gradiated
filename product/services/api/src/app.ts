import { apiReference } from "@scalar/hono-api-reference";
import { OpenAPIHono } from "@hono/zod-openapi";
import { bodyLimit } from "hono/body-limit";
import { cors } from "hono/cors";
import { requestId } from "hono/request-id";

import {
  registerAuthTestRoutes,
  type AuthTestMailbox,
} from "./auth/test-routes.js";
import { problemResponse, problems, toApiProblem } from "./http/problems.js";
import { apiRateLimit } from "./http/request-limits.js";
import { requestLogFields, serviceLog } from "./logging.js";
import { routeLabel, type ApiMetrics } from "./metrics.js";
import type { DependencyCheck } from "./readiness.js";
import { isConsoleOnly } from "./http/audience.js";
import { resolveCredentialUser } from "./auth/workspace-credential.js";
import { registerBillingRoutes } from "./routes/billing.js";
import { registerGatewayContract } from "./routes/gateway-contract.js";
import { registerHealthRoutes } from "./routes/health.js";
import { registerMeRoutes } from "./routes/me.js";
import { registerModelRoutes } from "./routes/models.js";
import { createExternalModelCatalog } from "./catalog/external-models.js";
import { registerMemberRoutes } from "./routes/members.js";
import { registerImpersonationRoutes } from "./routes/impersonation.js";
import { registerOrganizationRoutes } from "./routes/organizations.js";
import { registerNdaDocumentRoutes } from "./routes/nda-documents.js";
import { registerEngineerOnboardingRoutes } from "./routes/engineer-onboarding.js";
import { requireOnboardingAdmin } from "./http/onboarding-access.js";
import type { PandaDocNda } from "./legal/pandadoc.js";
import { registerSlackInvitationRoutes } from "./routes/slack-invitations.js";
import type { SlackConnect } from "./slack/connect.js";
import { registerGithubInstallationRoutes } from "./routes/github-installations.js";
import type { GithubInstallations } from "./github/installations.js";
import { registerUsageRoutes } from "./routes/usage.js";
import { registerWaitlistRoutes } from "./routes/waitlist.js";
import { registerWizardRoutes } from "./routes/wizard.js";
import { registerGenerationRoutes } from "./routes/generations.js";
import { registerTrainingRoutes } from "./routes/training.js";
import { registerWorkspaceRoutes } from "./routes/workspaces.js";
import type {
  ApiEnvironment,
  ApiServices,
  AuthService,
  SessionUser,
} from "./types.js";
import type { InvitationSender } from "./email/invitation.js";
import type { WaitlistWelcomeSender } from "./email/waitlist-welcome.js";
import type { EngineerOnboardingNotifier } from "./email/engineer-onboarding.js";

export interface AppDependencies {
  githubInstallations?: GithubInstallations | undefined;
  slackConnect?: SlackConnect | undefined;
  ndaDocuments?: PandaDocNda | undefined;
  analytics?: import("./analytics.js").ApiAnalytics;
  allowedOrigins: string[];
  auth: AuthService;
  authTestMailbox?: AuthTestMailbox | undefined;
  checkDependencies: DependencyCheck;
  consoleUrl: string;
  metrics: ApiMetrics;
  sendInvitation: InvitationSender;
  sendWaitlistWelcome: WaitlistWelcomeSender;
  notifyEngineerOnboarding: EngineerOnboardingNotifier;
  services: ApiServices;
  externalModels?: ReturnType<typeof createExternalModelCatalog>;
}

const ONBOARDING_RATE_LIMITS = [
  ["engineer-onboarding", 60],
  ["nda-documents", 60],
  ["slack-invitations", 5],
  ["github-installations", 30],
] as const;

export const createApp = ({
  githubInstallations,
  slackConnect,
  ndaDocuments,
  analytics,
  allowedOrigins,
  auth,
  authTestMailbox,
  checkDependencies,
  consoleUrl,
  metrics,
  sendInvitation,
  sendWaitlistWelcome,
  notifyEngineerOnboarding,
  services,
  externalModels = createExternalModelCatalog(),
}: AppDependencies) => {
  const app = new OpenAPIHono<ApiEnvironment>({
    defaultHook: (result, context) => {
      if (result.success) return;

      return problemResponse(
        context,
        problems.validation(
          result.error.issues.map((issue) => ({
            path: issue.path.join("."),
            message: issue.message,
          })),
        ),
      );
    },
  });

  app.use("*", async (context, next) => {
    if (analytics) context.set("analytics", analytics);
    await next();
  });
  app.use("*", metrics.middleware);
  app.use("*", requestId());
  app.use(
    "/api/*",
    cors({
      origin: allowedOrigins,
      credentials: true,
      exposeHeaders: ["X-Request-Id", "Retry-After", "RateLimit-Remaining"],
    }),
  );

  app.use("*", async (context, next) => {
    await next();
    context.header("X-Request-Id", context.get("requestId"));
  });

  app.use("/api/*", apiRateLimit());
  app.use("/api/v1/waitlist", apiRateLimit(10));
  for (const [path, limit] of ONBOARDING_RATE_LIMITS)
    app.use(
      `/api/v1/organizations/:organization_id/${path}/*`,
      apiRateLimit(limit),
    );
  app.use(
    "/api/v1/organizations/:organization_id/nda-documents/:document_id/signing-sessions",
    apiRateLimit(5),
  );
  app.use(
    "/api/v1/organizations/:organization_id/engineer-onboarding/submission",
    apiRateLimit(5),
  );
  app.use(
    "/api/*",
    bodyLimit({
      maxSize: 1024 * 1024,
      onError: (context) => problemResponse(context, problems.payloadTooLarge),
    }),
  );

  app.use("*", async (context, next) => {
    let session: Promise<SessionUser | null> | undefined;
    context.set("resolveUser", () => {
      session ??= auth
        .resolveSession(context.req.raw.headers)
        .then(
          (user) =>
            user ??
            resolveCredentialUser(services.workspaces, {
              headers: context.req.raw.headers,
              path: context.req.path,
            }),
        )
        .then((user) => {
          if (user) context.set("sessionUser", user);

          return user;
        });

      return session;
    });
    await next();
  });

  if (authTestMailbox) registerAuthTestRoutes(app, authTestMailbox);
  app.on(["GET", "POST"], "/api/auth/*", (context) =>
    auth.handler(context.req.raw),
  );

  registerHealthRoutes(app, {
    check: checkDependencies,
    observe: metrics.recordDependencies,
  });
  registerModelRoutes(app, services.catalogBilling, externalModels);
  registerBillingRoutes(app, {
    accounts: services.catalogBilling,
    payments: services.billingPayments,
  });
  registerMeRoutes(app, services.organizations);
  registerImpersonationRoutes(app, auth);
  registerOrganizationRoutes(app, services.organizations);
  registerNdaDocumentRoutes(app, services.organizations, ndaDocuments);
  registerGithubInstallationRoutes(
    app,
    services.organizations,
    auth,
    githubInstallations,
  );
  registerSlackInvitationRoutes(app, services, slackConnect);
  registerEngineerOnboardingRoutes(app, {
    organizations: services.organizations,
    integrations: services.integrations,
    auth,
    notify: notifyEngineerOnboarding,
    nda: ndaDocuments,
    slack: slackConnect,
    github: githubInstallations,
  });
  // Local test mode only, like the auth test routes: walk onboarding again.
  if (authTestMailbox)
    app.delete(
      "/api/v1/organizations/:organization_id/engineer-onboarding/submission",
      async (context) => {
        const organizationId = context.req.param("organization_id");
        const { owner } = await requireOnboardingAdmin(
          context,
          services.organizations,
          organizationId,
        );
        await services.organizations.resetOnboardingSubmission(
          owner.userId,
          organizationId,
        );
        return context.body(null, 204);
      },
    );
  registerMemberRoutes(app, {
    members: services.members,
    organizations: services.organizations,
    sendInvitation,
    consoleUrl,
  });
  registerUsageRoutes(app, services.usage);
  registerWaitlistRoutes(app, {
    waitlist: services.waitlist,
    sendWelcome: sendWaitlistWelcome,
  });
  registerWizardRoutes(app, {
    organizations: services.organizations,
    billingAccounts: services.catalogBilling,
    apiKeys: services.workspaces,
  });
  registerWorkspaceRoutes(app, services.workspaces);
  registerGenerationRoutes(app, services.usage, services.traces);
  registerTrainingRoutes(app, services.training);
  registerGatewayContract(app);

  // RFC 8414 places the metadata of the /api/auth issuer under this path on the origin.
  for (const path of [
    "/.well-known/oauth-authorization-server/api/auth",
    "/.well-known/oauth-authorization-server",
  ])
    app.get(path, (context) =>
      auth.authorizationServerMetadata(context.req.raw),
    );

  app.get("/api/openapi.json", (context) =>
    context.json(publicOpenApiDocument(app)),
  );
  app.get(
    "/docs",
    apiReference({
      pageTitle: "Gradiated API",
      sources: [{ title: "Gradiated API", url: "/api/openapi.json" }],
    }),
  );

  app.notFound((context) =>
    problemResponse(
      context,
      problems.notFound("The requested resource does not exist."),
    ),
  );

  app.onError((error, context) => {
    const request = {
      ...requestLogFields(context),
      method: context.req.method,
      route: routeLabel(context.req.routePath),
    };
    const apiProblem = toApiProblem(error);
    if (!apiProblem) {
      serviceLog("error", "request_failed", { error, ...request, status: 500 });
      return problemResponse(context, problems.internal);
    }

    if (apiProblem.problem.status >= 500) {
      serviceLog("error", "request_problem", {
        error: apiProblem.cause ?? error,
        ...request,
        status: apiProblem.problem.status,
      });
    }

    return problemResponse(context, apiProblem.problem);
  });

  return app;
};

export const openApiDocument = {
  openapi: "3.1.0" as const,
  info: {
    title: "Gradiated API",
    version: "0.1.0",
    description:
      "The Gradiated API covers inference, model discovery, workspaces, billing, API keys and usage. Inference endpoints use workspace API keys (Authorization: Bearer or x-api-key). Protected management endpoints require a signed-in user session and the appropriate organization role. A workspace API key also authorizes the workspace endpoints under /api/v1/workspaces/{workspace_id} for its own workspace, acting as the member who created it, except API key and playground credential management and changes to the workspace itself. Management request bodies are limited to 1 MiB (413 if exceeded). Management per-IP limits are 300 requests/minute, or 10/minute for waitlist signups, per API process. Engineer onboarding routes have lower per-route limits. Rate-limited requests return 429 with Retry-After. Stripe webhooks are excluded from the IP rate limits.",
  },
  servers: [{ url: "/", description: "Current origin" }],
  tags: [
    {
      name: "Inference",
      description:
        "OpenAI, Anthropic and native SystemOne inference served by the gateway.",
    },
    { name: "Session", description: "Current human session context." },
    { name: "Organizations", description: "Customer organization lifecycle." },
    { name: "Workspaces", description: "Usage and policy boundaries." },
    { name: "API keys", description: "Direct inference credentials." },
    { name: "Models", description: "Advertised exact-model catalog." },
    { name: "Billing", description: "Balances and durable movements." },
    {
      name: "Usage",
      description: "Inference activity and generation history.",
    },
  ],
};

export type OpenApiDocument = ReturnType<
  OpenAPIHono<ApiEnvironment>["getOpenAPI31Document"]
>;

export const clientOpenApiDocument = (
  app: OpenAPIHono<ApiEnvironment>,
): OpenApiDocument => {
  const document = app.getOpenAPI31Document(openApiDocument);
  document.paths = Object.fromEntries(
    Object.entries(document.paths ?? {}).filter(
      ([path]) =>
        path !== "/api/internal" && !path.startsWith("/api/internal/"),
    ),
  );

  return document;
};

export const publicOpenApiDocument = (
  app: OpenAPIHono<ApiEnvironment>,
): OpenApiDocument => {
  const document = clientOpenApiDocument(app);
  document.paths = Object.fromEntries(
    Object.entries(document.paths ?? {}).flatMap(([path, item]) => {
      const operations = Object.entries(item ?? {}).filter(
        ([, operation]) => !isConsoleOnly(operation),
      );

      return operations.length > 0
        ? [[path, Object.fromEntries(operations)]]
        : [];
    }),
  );

  return document;
};
