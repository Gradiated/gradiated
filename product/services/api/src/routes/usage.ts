import {
  GenerationListQuerySchema,
  GenerationListSchema,
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
  path: "/api/v1/organizations/{organization_id}/workspaces/{workspace_id}/usage",
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

const listGenerationsRoute = createRoute({
  method: "get",
  path: "/api/v1/organizations/{organization_id}/workspaces/{workspace_id}/generations",
  operationId: "listGenerations",
  tags: ["Usage"],
  request: { params: WorkspacePathSchema, query: GenerationListQuerySchema },
  responses: {
    200: {
      description: "Terminal generations for the selected workspace.",
      content: { "application/json": { schema: GenerationListSchema } },
    },
    401: {
      description: "Authentication is required.",
      content: problemContent,
    },
    404: {
      description: "The workspace was not found.",
      content: problemContent,
    },
    422: { description: "The filters are invalid.", content: problemContent },
    503: {
      description: "Generation logs are unavailable.",
      content: problemContent,
    },
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
      organizationId: params.organization_id,
      workspaceId: params.workspace_id,
      range: { from: new Date(query.from), to: new Date(query.to) },
    });

    return context.json(usageSummaryResponse(summary), 200);
  });

  app.openapi(listGenerationsRoute, async (context) => {
    const user = await requireUser(context);
    const params = context.req.valid("param");
    const query = context.req.valid("query");
    const generations = await usage.listGenerations({
      userId: user.id,
      organizationId: params.organization_id,
      workspaceId: params.workspace_id,
      range: { from: new Date(query.from), to: new Date(query.to) },
      limit: query.limit,
      sort: query.sort,
      ...(query.api_key_id ? { apiKeyId: query.api_key_id } : {}),
      ...(query.cursor ? { cursor: query.cursor } : {}),
      ...(query.model ? { model: query.model } : {}),
      ...(query.search ? { search: query.search } : {}),
      ...(query.status ? { status: query.status } : {}),
    });

    return context.json(
      {
        data: generations.data,
        next_cursor: generations.nextCursor,
      },
      200,
    );
  });
};
