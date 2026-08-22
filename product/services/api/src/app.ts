import { apiReference } from "@scalar/hono-api-reference";
import { OpenAPIHono } from "@hono/zod-openapi";
import { cors } from "hono/cors";
import { requestId } from "hono/request-id";

import { unavailableBillingPaymentsService } from "./billing/stripe.js";
import { problemResponse } from "./http/problem-response.js";
import { ApiMetrics } from "./metrics.js";
import { registerCatalogBillingRoutes } from "./routes/catalog-billing.js";
import { registerHealthRoutes, type DependencyCheck } from "./routes/health.js";
import { registerMeRoutes } from "./routes/me.js";
import { registerOrganizationRoutes } from "./routes/organizations.js";
import { registerWorkspaceRoutes } from "./routes/workspaces.js";
import type { ApiEnvironment, ApiServices, AuthService } from "./types.js";

export interface AppDependencies {
  allowedOrigins: string[];
  checkDependencies: DependencyCheck;
  metrics: ApiMetrics;
  auth?: AuthService;
  services: ApiServices;
}

export interface AppOverrides extends Omit<
  Partial<AppDependencies>,
  "services"
> {
  services?: Partial<ApiServices>;
}

const defaultDependencies: AppDependencies = {
  allowedOrigins: [],
  checkDependencies: async () => ({}),
  metrics: new ApiMetrics({ collectProcessMetrics: false }),
  services: {
    billingPayments: unavailableBillingPaymentsService(),
    catalogBilling: {
      listModels: async () => [],
      getBillingAccount: async () => {
        throw new Error("Catalog and billing service is not configured");
      },
      listBalanceTransactions: async () => [],
      upsertModel: async () => {
        throw new Error("Catalog and billing service is not configured");
      },
      upsertModelDeployment: async () => {
        throw new Error("Catalog and billing service is not configured");
      },
      initializeCurrentAccount: async () => {
        throw new Error("Catalog and billing service is not configured");
      },
      projectCurrentAccount: async () => {
        throw new Error("Catalog and billing service is not configured");
      },
      applyBalanceTransaction: async () => {
        throw new Error("Catalog and billing service is not configured");
      },
    },
    organizations: {
      listForUser: async () => [],
      createForUser: async () => {
        throw new Error("Organization service is not configured");
      },
      ensurePersonalForUser: async () => {
        throw new Error("Organization service is not configured");
      },
    },
    workspaces: {
      listWorkspaces: async () => [],
      createWorkspace: async () => {
        throw new Error("Workspace service is not configured");
      },
      listApiKeys: async () => [],
      createApiKey: async () => {
        throw new Error("Workspace service is not configured");
      },
      revokeApiKey: async () => {
        throw new Error("Workspace service is not configured");
      },
    },
  },
};

export const createApp = (overrides: AppOverrides = {}) => {
  const dependencies: AppDependencies = {
    ...defaultDependencies,
    ...overrides,
    services: {
      ...defaultDependencies.services,
      ...overrides.services,
    },
  };
  const app = new OpenAPIHono<ApiEnvironment>({
    defaultHook: (result, context) => {
      if (result.success) return;

      return problemResponse(context, {
        type: "https://gradiated.com/problems/validation",
        title: "Request validation failed",
        status: 422,
        detail: "The request does not match the operation contract.",
        code: "validation_failed",
        errors: result.error.issues.map((issue) => ({
          path: issue.path.join("."),
          message: issue.message,
        })),
      });
    },
  });

  app.use("*", dependencies.metrics.middleware);
  app.use("*", requestId());
  app.use(
    "/api/*",
    cors({
      origin: dependencies.allowedOrigins,
      credentials: true,
      exposeHeaders: ["X-Request-Id"],
    }),
  );
  app.use("*", async (context, next) => {
    await next();
    context.header("X-Request-Id", context.get("requestId"));
  });
  app.use("/api/v1/*", async (context, next) => {
    const user = dependencies.auth
      ? await dependencies.auth.resolveSession(context.req.raw.headers)
      : null;
    context.set("user", user);
    await next();
  });

  if (dependencies.auth) {
    if (dependencies.auth.takeTestMagicLink) {
      app.get("/api/auth/test/magic-link", (context) => {
        const email = context.req.query("email");
        if (!email) return context.json({ error: "Email is required." }, 400);
        const url = dependencies.auth!.takeTestMagicLink!(email);
        if (!url) return context.json({ error: "Link not found." }, 404);
        return context.json({ url });
      });
    }
    app.on(["GET", "POST"], "/api/auth/*", (context) =>
      dependencies.auth!.handler(context.req.raw),
    );
  }

  registerHealthRoutes(
    app,
    dependencies.checkDependencies,
    dependencies.metrics.recordDependencies.bind(dependencies.metrics),
  );
  registerCatalogBillingRoutes(app, dependencies.services);
  registerMeRoutes(app, dependencies.services);
  registerOrganizationRoutes(app, dependencies.services);
  registerWorkspaceRoutes(app, dependencies.services);

  app.doc31("/api/openapi.json", openApiDocument);
  app.get(
    "/docs",
    apiReference({
      pageTitle: "Gradiated API",
      sources: [
        { title: "Product API", url: "/api/openapi.json" },
        ...(dependencies.auth
          ? [
              {
                title: "Authentication API",
                url: "/api/auth/open-api/generate-schema",
              },
            ]
          : []),
      ],
    }),
  );

  app.notFound((context) =>
    problemResponse(context, {
      type: "https://gradiated.com/problems/not-found",
      title: "Not found",
      status: 404,
      detail: "The requested resource does not exist.",
      code: "not_found",
    }),
  );

  app.onError((error, context) => {
    console.error("Unhandled API error", {
      error,
      request_id: context.get("requestId"),
    });
    return problemResponse(context, {
      type: "https://gradiated.com/problems/internal",
      title: "Internal server error",
      status: 500,
      detail: "The server could not complete the request.",
      code: "internal_error",
    });
  });

  return app;
};

export const openApiDocument = {
  openapi: "3.1.0" as const,
  info: {
    title: "Gradiated Product API",
    version: "0.1.0",
    description: "Application API for Gradiated exact-model inference.",
  },
  servers: [{ url: "/", description: "Current origin" }],
  tags: [
    { name: "System", description: "Process health and readiness." },
    { name: "Session", description: "Current human session context." },
    { name: "Organizations", description: "Customer organization lifecycle." },
    { name: "Workspaces", description: "Usage and policy boundaries." },
    { name: "API keys", description: "Direct inference credentials." },
    { name: "Models", description: "Advertised exact-model catalog." },
    { name: "Billing", description: "Balances and durable movements." },
  ],
};
