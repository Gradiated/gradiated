import { createRoute, type OpenAPIHono, z } from "@hono/zod-openapi";
import { problemContent } from "@gradiated/contracts";

import { problemResponse, problems } from "../http/problems.js";
import type { ApiEnvironment } from "../types.js";
import type { DependencyCheck, DependencyChecks } from "../readiness.js";

const HealthStatusSchema = z
  .object({ status: z.literal("live") })
  .openapi("HealthStatus");

const ReadinessSchema = z
  .object({
    status: z.literal("ready"),
    checks: z.record(z.string(), z.enum(["up", "down"])),
  })
  .openapi("Readiness");

const livenessRoute = createRoute({
  hide: true,
  method: "get",
  path: "/health/live",
  operationId: "getLiveness",
  tags: ["System"],
  responses: {
    200: {
      description: "The API process is live.",
      content: { "application/json": { schema: HealthStatusSchema } },
    },
  },
});

const readinessRoute = createRoute({
  hide: true,
  method: "get",
  path: "/health/ready",
  operationId: "getReadiness",
  tags: ["System"],
  responses: {
    200: {
      description: "The API is ready to serve product traffic.",
      content: { "application/json": { schema: ReadinessSchema } },
    },
    503: {
      description: "At least one required dependency is unavailable.",
      content: problemContent,
    },
  },
});

export const registerHealthRoutes = (
  app: OpenAPIHono<ApiEnvironment>,
  dependencies: {
    check: DependencyCheck;
    observe: (checks: DependencyChecks) => void;
  },
): void => {
  app.openapi(livenessRoute, (context) =>
    context.json({ status: "live" as const }, 200),
  );

  app.openapi(readinessRoute, async (context) => {
    const probes = await dependencies.check();
    dependencies.observe(probes);

    const checks = Object.fromEntries(
      Object.entries(probes).map(([name, probe]) => [name, probe.status]),
    );
    if (Object.values(checks).every((status) => status === "up")) {
      return context.json({ status: "ready" as const, checks }, 200);
    }

    return problemResponse(context, problems.notReady);
  });
};
