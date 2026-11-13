import { createRoute, type OpenAPIHono } from "@hono/zod-openapi";
import {
  GenerationsQuerySchema,
  GenerationListQuerySchema,
  GenerationsListSchema,
  TraceContentPathSchema,
  TraceContentQuerySchema,
  TraceContentSchema,
  WorkspacePathSchema,
  problemContent,
} from "@gradiated/contracts";
import type { TraceService, UsageService } from "@gradiated/control";
import { requireUser } from "../http/problems.js";
import type { ApiEnvironment } from "../types.js";

const base = "/api/v1/workspaces/{workspace_id}";
const errors = {
  401: { description: "Authentication required.", content: problemContent },
  404: { description: "Generation not found.", content: problemContent },
  422: {
    description: "Invalid generation reference.",
    content: problemContent,
  },
  503: {
    description: "Generation content unavailable.",
    content: problemContent,
  },
};
const listGenerationsRoute = createRoute({
  method: "get",
  path: "/api/v1/workspaces/{workspace_id}/generations",
  operationId: "listGenerations",
  summary: "List generations",
  description: "Lists the workspace's inference requests.",
  tags: ["Generations"],
  request: { params: WorkspacePathSchema, query: GenerationsQuerySchema },
  responses: {
    200: {
      description:
        "Workspace generations. With task_id, returns captured metadata from S3; date-range queries return hosted usage logs.",
      content: { "application/json": { schema: GenerationsListSchema } },
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

const content = createRoute({
  method: "get",
  path: `${base}/generations/{generation_id}`,
  operationId: "getGeneration",
  summary: "Get generation",
  description:
    "Gets one captured generation's stored request and response. Content is stored only for generations captured for a task; locate it with the task's name or the content_ref from listing the task's generations.",
  tags: ["Generations"],
  request: { params: TraceContentPathSchema, query: TraceContentQuerySchema },
  responses: {
    200: {
      description: "Stored generation request and response.",
      content: { "application/json": { schema: TraceContentSchema } },
    },
    ...errors,
  },
});
export const registerGenerationRoutes = (
  app: OpenAPIHono<ApiEnvironment>,
  usage: UsageService,
  traces: TraceService,
) => {
  app.openapi(listGenerationsRoute, async (context) => {
    const user = await requireUser(context);
    const params = context.req.valid("param");
    const filters = context.req.valid("query");
    if (filters.task_id !== undefined) {
      const page = await traces.list(user.id, params.workspace_id, {
        task: filters.task_id,
        ...(filters.cursor ? { cursor: filters.cursor } : {}),
      });
      context.header("Cache-Control", "no-store");
      return context.json(page, 200);
    }

    const query = GenerationListQuerySchema.parse(filters);
    const generations = await usage.listGenerations({
      userId: user.id,
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
  app.openapi(content, async (c) => {
    const user = await requireUser(c);
    const p = c.req.valid("param");
    const query = c.req.valid("query");
    c.header("Cache-Control", "no-store");
    return c.json(
      await traces.content(
        user.id,
        p.workspace_id,
        p.generation_id,
        // The schema requires exactly one of them.
        query.content_ref === undefined
          ? { task: query.task_id! }
          : { content_ref: query.content_ref },
      ),
      200,
    );
  });
};
