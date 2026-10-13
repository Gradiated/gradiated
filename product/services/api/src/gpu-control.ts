import { OpenAPIHono } from "@hono/zod-openapi";
import { bodyLimit } from "hono/body-limit";
import type { DeploymentStatusService } from "@gradiated/control";

import { apiRateLimit } from "./http/request-limits.js";
import { problemResponse, problems } from "./http/problems.js";
import { createDeploymentStatusIngestApp } from "./ingest/deployment-status.js";
import { registerHealthRoutes } from "./routes/health.js";
import {
  createHostCertificateRouter,
  type HostCertificateDependencies,
} from "./routes/instance-certificates.js";
import {
  registerAdapterHostingRoutes,
  type AdapterHostingDependencies,
} from "./routes/adapter-hosting.js";
import type { DependencyCheck } from "./readiness.js";
import type { ApiEnvironment } from "./types.js";

export const createGpuControlApp = (dependencies: {
  provider: string;
  status: DeploymentStatusService;
  certificates?: HostCertificateDependencies;
  adapters?: Pick<AdapterHostingDependencies, "service">;
  check: DependencyCheck;
}) => {
  const app = new OpenAPIHono<ApiEnvironment>();
  app.use("/api/*", apiRateLimit());
  app.use(
    "/api/*",
    bodyLimit({
      maxSize: 1024 * 1024,
      onError: (context) => problemResponse(context, problems.payloadTooLarge),
    }),
  );
  registerHealthRoutes(app, {
    check: dependencies.check,
    observe: () => undefined,
  });
  app.route(
    "/",
    createDeploymentStatusIngestApp({
      provider: dependencies.provider,
      service: dependencies.status,
    }),
  );
  if (dependencies.certificates)
    app.route("/", createHostCertificateRouter(dependencies.certificates));
  if (dependencies.adapters)
    registerAdapterHostingRoutes(app, dependencies.adapters, true);
  return app;
};
