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
import { registerBillingRoutes } from "./routes/billing.js";
import { registerHealthRoutes } from "./routes/health.js";
import { registerMeRoutes } from "./routes/me.js";
import { registerModelRoutes } from "./routes/models.js";
import { registerOrganizationRoutes } from "./routes/organizations.js";
import { registerSystemOneContract } from "./routes/systemone-contract.js";
import { registerUsageRoutes } from "./routes/usage.js";
import { registerWaitlistRoutes } from "./routes/waitlist.js";
import { registerWizardRoutes } from "./routes/wizard.js";
import { registerGenerationRoutes } from "./routes/generations.js";
import { registerWorkspaceRoutes } from "./routes/workspaces.js";
import type {
  ApiEnvironment,
  ApiServices,
  AuthService,
  SessionUser,
} from "./types.js";
import type { WaitlistWelcomeSender } from "./email/waitlist-welcome.js";

export interface AppDependencies {
  allowedOrigins: string[];
  auth: AuthService;
  authTestMailbox?: AuthTestMailbox | undefined;
  checkDependencies: DependencyCheck;
  metrics: ApiMetrics;
  sendWaitlistWelcome: WaitlistWelcomeSender;
  services: ApiServices;
}

export const createApp = ({
  allowedOrigins,
  auth,
  authTestMailbox,
  checkDependencies,
  metrics,
  sendWaitlistWelcome,
  services,
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
      session ??= auth.resolveSession(context.req.raw.headers).then((user) => {
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
  registerModelRoutes(app, services.catalogBilling);
  registerBillingRoutes(app, {
    accounts: services.catalogBilling,
    payments: services.billingPayments,
  });
  registerMeRoutes(app, services.organizations);
  registerOrganizationRoutes(app, services.organizations);
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
  registerSystemOneContract(app);

  app.doc31("/api/openapi.json", openApiDocument);
  app.get(
    "/docs",
    apiReference({
      pageTitle: "Gradiated Management API",
      sources: [{ title: "Management API", url: "/api/openapi.json" }],
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
    title: "Gradiated Management API",
    version: "0.1.0",
    description:
      "Use the Management API to manage workspaces, billing limits, workspace members and model availability. Request bodies are limited to 1 MiB (413 if exceeded). Per-IP limits are 300 requests/minute, or 10/minute for waitlist signups, per API process. Rate-limited requests return 429 with Retry-After. Stripe webhooks are excluded from the IP rate limits.",
  },
  servers: [{ url: "/", description: "Current origin" }],
  tags: [
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
