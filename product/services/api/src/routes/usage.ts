import {
  UsageQuerySchema,
  UsageSummarySchema,
  WorkspacePathSchema,
  problemContent,
  type UsageSummary,
} from "@gradiated/contracts";
import type { UsageService, UsageSummaryRecord } from "@gradiated/control";
import { createRoute, type OpenAPIHono } from "@hono/zod-openapi";

import { requireUser } from "../http/problems.js";
import type { ApiEnvironment } from "../types.js";

const getUsageSummaryRoute = createRoute({
  method: "get",
  path: "/api/v1/workspaces/{workspace_id}/usage",
  operationId: "getUsageSummary",
  tags: ["Usage"],
  request: { params: WorkspacePathSchema, query: UsageQuerySchema },
  responses: {
    200: {
      description:
        "Usage totals and daily breakdowns for the selected workspace.",
      content: { "application/json": { schema: UsageSummarySchema } },
    },
    401: {
      description: "Authentication is required.",
      content: problemContent,
    },
    404: {
      description: "The workspace was not found.",
      content: problemContent,
    },
    422: { description: "The date range is invalid.", content: problemContent },
    503: { description: "Usage data is unavailable.", content: problemContent },
  },
});

const usageSummaryResponse = (summary: UsageSummaryRecord): UsageSummary => ({
  charge: summary.charge,
  input_tokens: summary.inputTokens,
  output_tokens: summary.outputTokens,
  generation_count: summary.generationCount,
  succeeded_count: summary.succeededCount,
  daily: summary.daily,
  models: summary.models,
});

export const registerUsageRoutes = (
  app: OpenAPIHono<ApiEnvironment>,
  usage: UsageService,
): void => {
  app.openapi(getUsageSummaryRoute, async (context) => {
    const user = await requireUser(context);
    const params = context.req.valid("param");
    const query = context.req.valid("query");
    const summary = await usage.getSummary({
      userId: user.id,
      workspaceId: params.workspace_id,
      range: { from: new Date(query.from), to: new Date(query.to) },
    });

    return context.json(usageSummaryResponse(summary), 200);
  });
};
