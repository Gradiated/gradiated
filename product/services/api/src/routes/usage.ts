import {
  GenerationListQuerySchema,
  GenerationListSchema,
  UsageQuerySchema,
  UsageSummarySchema,
  WorkspacePathSchema,
  problemContent,
  type GenerationLog,
  type UsageSummary,
} from "@gradiated/contracts";
import { ControlServiceError } from "@gradiated/control";
import { createRoute, type OpenAPIHono } from "@hono/zod-openapi";

import { problemDocument } from "../http/problem-response.js";
import type { ApiEnvironment, ApiServices } from "../types.js";

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

const unauthenticated = (context: Parameters<typeof problemDocument>[0]) =>
  context.json(
    problemDocument(context, {
      type: "https://gradiated.com/problems/unauthenticated",
      title: "Authentication required",
      status: 401,
      detail: "A valid human session is required for this operation.",
      code: "unauthenticated",
    }),
    401,
    { "Content-Type": "application/problem+json" },
  );

const usageError = (
  context: Parameters<typeof problemDocument>[0],
  error: unknown,
) => {
  if (!(error instanceof ControlServiceError)) throw error;
  const unavailable = error.code === "unavailable";
  const status = unavailable ? 503 : 404;
  return context.json(
    problemDocument(context, {
      type: `https://gradiated.com/problems/${unavailable ? "usage-unavailable" : "not-found"}`,
      title: unavailable ? "Usage unavailable" : "Not found",
      status,
      detail: error.message,
      code: error.code,
    }),
    status,
    { "Content-Type": "application/problem+json" },
  );
};

const usageSummaryResponse = (
  summary: Awaited<ReturnType<ApiServices["usage"]["getSummary"]>>,
): UsageSummary => ({
  charge: summary.charge,
  input_tokens: summary.inputTokens,
  output_tokens: summary.outputTokens,
  generation_count: summary.generationCount,
  succeeded_count: summary.succeededCount,
  daily: summary.daily,
  models: summary.models,
});

const generationResponse = (
  generation: Awaited<
    ReturnType<ApiServices["usage"]["listGenerations"]>
  >["data"][number],
): GenerationLog => generation;

export const registerUsageRoutes = (
  app: OpenAPIHono<ApiEnvironment>,
  services: ApiServices,
): void => {
  app.openapi(getUsageSummaryRoute, async (context) => {
    const user = context.get("user");
    if (!user) return unauthenticated(context);
    const params = context.req.valid("param");
    const query = context.req.valid("query");
    try {
      const summary = await services.usage.getSummary({
        userId: user.id,
        organizationId: params.organization_id,
        workspaceId: params.workspace_id,
        range: { from: new Date(query.from), to: new Date(query.to) },
      });
      return context.json(usageSummaryResponse(summary), 200);
    } catch (error) {
      return usageError(context, error);
    }
  });

  app.openapi(listGenerationsRoute, async (context) => {
    const user = context.get("user");
    if (!user) return unauthenticated(context);
    const params = context.req.valid("param");
    const query = context.req.valid("query");
    try {
      const generations = await services.usage.listGenerations({
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
          data: generations.data.map(generationResponse),
          next_cursor: generations.nextCursor,
        },
        200,
      );
    } catch (error) {
      return usageError(context, error);
    }
  });
};
