import {
  ApiKeyListSchema,
  ApiKeyPathSchema,
  ApiKeySchema,
  CreateApiKeySchema,
  CreateWorkspaceSchema,
  CreatedApiKeySchema,
  OrganizationIdParamsSchema,
  WorkspaceListQuerySchema,
  WorkspaceListSchema,
  WorkspacePathSchema,
  WorkspaceSchema,
  problemContent,
  type Workspace,
} from "@gradiated/contracts";
import type {
  WorkspaceApiKeyService,
  WorkspaceRecord,
} from "@gradiated/control";
import { createRoute, type OpenAPIHono } from "@hono/zod-openapi";

import { requireUser } from "../http/problems.js";
import type { ApiEnvironment } from "../types.js";
import { apiKeyResponse } from "./api-key-response.js";

const listWorkspacesRoute = createRoute({
  method: "get",
  path: "/api/v1/organizations/{organization_id}/workspaces",
  operationId: "listWorkspaces",
  tags: ["Workspaces"],
  request: {
    params: OrganizationIdParamsSchema,
    query: WorkspaceListQuerySchema,
  },
  responses: {
    200: {
      description: "The organization's accessible workspaces.",
      content: { "application/json": { schema: WorkspaceListSchema } },
    },
    401: {
      description: "Authentication is required.",
      content: problemContent,
    },
  },
});

const createWorkspaceRoute = createRoute({
  method: "post",
  path: "/api/v1/organizations/{organization_id}/workspaces",
  operationId: "createWorkspace",
  tags: ["Workspaces"],
  request: {
    params: OrganizationIdParamsSchema,
    body: {
      required: true,
      content: { "application/json": { schema: CreateWorkspaceSchema } },
    },
  },
  responses: {
    201: {
      description: "A workspace in the selected organization.",
      content: { "application/json": { schema: WorkspaceSchema } },
    },
    401: {
      description: "Authentication is required.",
      content: problemContent,
    },
    403: {
      description: "The caller cannot create workspaces.",
      content: problemContent,
    },
    404: {
      description: "The organization was not found.",
      content: problemContent,
    },
    422: {
      description: "The request body is invalid.",
      content: problemContent,
    },
    503: {
      description: "Application state is unavailable.",
      content: problemContent,
    },
  },
});

const listApiKeysRoute = createRoute({
  method: "get",
  path: "/api/v1/organizations/{organization_id}/workspaces/{workspace_id}/api-keys",
  operationId: "listApiKeys",
  tags: ["API keys"],
  request: { params: WorkspacePathSchema },
  responses: {
    200: {
      description: "API-key metadata for the selected workspace.",
      content: { "application/json": { schema: ApiKeyListSchema } },
    },
    401: {
      description: "Authentication is required.",
      content: problemContent,
    },
    403: {
      description: "The caller cannot access keys.",
      content: problemContent,
    },
    404: {
      description: "The workspace was not found.",
      content: problemContent,
    },
    503: {
      description: "Serving state is unavailable.",
      content: problemContent,
    },
  },
});

const createApiKeyRoute = createRoute({
  method: "post",
  path: "/api/v1/organizations/{organization_id}/workspaces/{workspace_id}/api-keys",
  operationId: "createApiKey",
  tags: ["API keys"],
  request: {
    params: WorkspacePathSchema,
    body: {
      required: true,
      content: { "application/json": { schema: CreateApiKeySchema } },
    },
  },
  responses: {
    201: {
      description: "The API key and its one-time secret.",
      headers: {
        "Cache-Control": {
          description: "Prevents storage of the one-time secret.",
          schema: { type: "string" },
        },
      },
      content: { "application/json": { schema: CreatedApiKeySchema } },
    },
    401: {
      description: "Authentication is required.",
      content: problemContent,
    },
    403: {
      description: "The caller cannot manage keys.",
      content: problemContent,
    },
    404: {
      description: "The workspace was not found.",
      content: problemContent,
    },
    422: {
      description: "The request body is invalid.",
      content: problemContent,
    },
    503: {
      description: "Serving state is unavailable.",
      content: problemContent,
    },
  },
});

const revokeApiKeyRoute = createRoute({
  method: "delete",
  path: "/api/v1/organizations/{organization_id}/workspaces/{workspace_id}/api-keys/{api_key_id}",
  operationId: "revokeApiKey",
  tags: ["API keys"],
  request: { params: ApiKeyPathSchema },
  responses: {
    204: { description: "The API key is revoked." },
    401: {
      description: "Authentication is required.",
      content: problemContent,
    },
    403: {
      description: "The caller cannot manage keys.",
      content: problemContent,
    },
    404: { description: "The API key was not found.", content: problemContent },
    503: {
      description: "Serving state is unavailable.",
      content: problemContent,
    },
  },
});

const workspaceResponse = (record: WorkspaceRecord): Workspace => ({
  id: record.id,
  organization_id: record.organizationId,
  name: record.name,
  is_default: record.isDefault,
  archived_at: record.archivedAt?.toISOString() ?? null,
  created_at: record.createdAt.toISOString(),
  updated_at: record.updatedAt.toISOString(),
});

export const registerWorkspaceRoutes = (
  app: OpenAPIHono<ApiEnvironment>,
  workspaces: WorkspaceApiKeyService,
): void => {
  app.openapi(listWorkspacesRoute, async (context) => {
    const user = await requireUser(context);
    const params = context.req.valid("param");
    const query = context.req.valid("query");
    const rows = await workspaces.listWorkspaces(
      user.id,
      params.organization_id,
      query.include_archived === "true",
    );

    return context.json(
      { data: rows.map(workspaceResponse), next_cursor: null },
      200,
    );
  });

  app.openapi(createWorkspaceRoute, async (context) => {
    const user = await requireUser(context);
    const params = context.req.valid("param");
    const input = context.req.valid("json");
    const workspace = await workspaces.createWorkspace(
      user.id,
      params.organization_id,
      input,
    );

    context.set("logResourceIds", { workspace_id: workspace.id });
    return context.json(workspaceResponse(workspace), 201);
  });

  app.openapi(listApiKeysRoute, async (context) => {
    const user = await requireUser(context);
    const params = context.req.valid("param");
    const rows = await workspaces.listApiKeys(
      user.id,
      params.organization_id,
      params.workspace_id,
    );

    return context.json(
      { data: rows.map(apiKeyResponse), next_cursor: null },
      200,
    );
  });

  app.openapi(createApiKeyRoute, async (context) => {
    const user = await requireUser(context);
    const params = context.req.valid("param");
    const input = context.req.valid("json");
    const created = await workspaces.createApiKey(
      user.id,
      params.organization_id,
      params.workspace_id,
      {
        name: input.name,
        expiresAt: input.expires_at ? new Date(input.expires_at) : null,
      },
    );

    context.set("logResourceIds", { api_key_id: created.apiKey.id });
    context.header("Cache-Control", "no-store");
    return context.json(
      { api_key: apiKeyResponse(created.apiKey), secret: created.secret },
      201,
    );
  });

  app.openapi(revokeApiKeyRoute, async (context) => {
    const user = await requireUser(context);
    const params = context.req.valid("param");
    await workspaces.revokeApiKey(
      user.id,
      params.organization_id,
      params.workspace_id,
      params.api_key_id,
    );

    return context.body(null, 204);
  });
};
