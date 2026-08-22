import { createRoute, type OpenAPIHono, z } from "@hono/zod-openapi";
import { problemContent } from "@gradiated/contracts";

import { problemDocument } from "../http/problem-response.js";
import type { ApiEnvironment } from "../types.js";

const HealthStatusSchema = z
  .object({
    status: z.enum(["live", "ready", "not_ready"]),
  })
  .openapi("HealthStatus");

const ReadinessSchema = HealthStatusSchema.extend({
  checks: z.record(z.string(), z.enum(["up", "down"])),
}).openapi("Readiness");

const livenessRoute = createRoute({
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

export type DependencyCheck = () => Promise<Record<string, "up" | "down">>;
export type DependencyCheckObserver = (
  checks: Record<string, "up" | "down">,
) => void;

export function registerHealthRoutes(
  app: OpenAPIHono<ApiEnvironment>,
  checkDependencies: DependencyCheck,
  observeDependencies: DependencyCheckObserver = () => undefined,
): void {
  app.openapi(livenessRoute, (context) =>
    context.json({ status: "live" as const }, 200),
  );

  app.openapi(readinessRoute, async (context) => {
    const checks = await checkDependencies();
    observeDependencies(checks);
    if (Object.values(checks).every((status) => status === "up")) {
      return context.json({ status: "ready" as const, checks }, 200);
    }

    return context.json(
      problemDocument(context, {
        type: "https://gradiated.com/problems/not-ready",
        title: "Service not ready",
        status: 503,
        detail:
          "At least one dependency required for product traffic is unavailable.",
        code: "not_ready",
      }),
      503,
      { "Content-Type": "application/problem+json" },
    );
  });
}
