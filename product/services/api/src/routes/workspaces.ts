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
  type ApiKey,
  type Workspace,
} from "@gradiated/contracts";
import { ControlServiceError } from "@gradiated/control";
import { createRoute, type OpenAPIHono } from "@hono/zod-openapi";

import { problemDocument } from "../http/problem-response.js";
import type { ApiEnvironment, ApiServices } from "../types.js";

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

function workspaceResponse(row: {
  id: string;
  organizationId: string;
  name: string;
  isDefault: boolean;
  archivedAt: Date | null;
  createdAt: Date;
  updatedAt: Date;
}): Workspace {
  return {
    id: row.id,
    organization_id: row.organizationId,
    name: row.name,
    is_default: row.isDefault,
    archived_at: row.archivedAt?.toISOString() ?? null,
    created_at: row.createdAt.toISOString(),
    updated_at: row.updatedAt.toISOString(),
  };
}

function apiKeyResponse(row: {
  id: string;
  organizationId: string;
  workspaceId: string;
  name: string;
  expiresAt: Date | null;
  revokedAt: Date | null;
  createdBy: string | null;
  createdAt: Date;
  updatedAt: Date;
}): ApiKey {
  return {
    id: row.id,
    organization_id: row.organizationId,
    workspace_id: row.workspaceId,
    name: row.name,
    expires_at: row.expiresAt?.toISOString() ?? null,
    revoked_at: row.revokedAt?.toISOString() ?? null,
    created_by: row.createdBy,
    created_at: row.createdAt.toISOString(),
    updated_at: row.updatedAt.toISOString(),
  };
}

function requireUser(context: {
  get(key: "user"): ApiEnvironment["Variables"]["user"];
}) {
  return context.get("user");
}

function controlError(
  context: Parameters<typeof problemDocument>[0],
  error: unknown,
) {
  if (!(error instanceof ControlServiceError)) throw error;
  if (error.code === "forbidden") {
    return context.json(
      problemDocument(context, {
        type: "https://gradiated.com/problems/forbidden",
        title: "Forbidden",
        status: 403,
        detail: error.message,
        code: error.code,
      }),
      403,
      { "Content-Type": "application/problem+json" },
    );
  }
  if (error.code === "not_found") {
    return context.json(
      problemDocument(context, {
        type: "https://gradiated.com/problems/not-found",
        title: "Not found",
        status: 404,
        detail: error.message,
        code: error.code,
      }),
      404,
      { "Content-Type": "application/problem+json" },
    );
  }
  return context.json(
    problemDocument(context, {
      type: "https://gradiated.com/problems/unavailable",
      title: "Serving state unavailable",
      status: 503,
      detail: error.message,
      code: error.code,
    }),
    503,
    { "Content-Type": "application/problem+json" },
  );
}

export function registerWorkspaceRoutes(
  app: OpenAPIHono<ApiEnvironment>,
  services: ApiServices,
): void {
  app.openapi(listWorkspacesRoute, async (context) => {
    const user = requireUser(context);
    if (!user) return unauthenticated(context);
    const params = context.req.valid("param");
    const query = context.req.valid("query");
    const rows = await services.workspaces.listWorkspaces(
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
    const user = requireUser(context);
    if (!user) return unauthenticated(context);
    const params = context.req.valid("param");
    const input = context.req.valid("json");
    try {
      const workspace = await services.workspaces.createWorkspace(
        user.id,
        params.organization_id,
        input,
      );
      context.set("logResourceIds", { workspace_id: workspace.id });
      return context.json(workspaceResponse(workspace), 201);
    } catch (error) {
      return controlError(context, error);
    }
  });

  app.openapi(listApiKeysRoute, async (context) => {
    const user = requireUser(context);
    if (!user) return unauthenticated(context);
    const params = context.req.valid("param");
    try {
      const rows = await services.workspaces.listApiKeys(
        user.id,
        params.organization_id,
        params.workspace_id,
      );
      return context.json(
        { data: rows.map(apiKeyResponse), next_cursor: null },
        200,
      );
    } catch (error) {
      return controlError(context, error);
    }
  });

  app.openapi(createApiKeyRoute, async (context) => {
    const user = requireUser(context);
    if (!user) return unauthenticated(context);
    const params = context.req.valid("param");
    const input = context.req.valid("json");
    try {
      const created = await services.workspaces.createApiKey(
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
    } catch (error) {
      return controlError(context, error);
    }
  });

  app.openapi(revokeApiKeyRoute, async (context) => {
    const user = requireUser(context);
    if (!user) return unauthenticated(context);
    const params = context.req.valid("param");
    try {
      await services.workspaces.revokeApiKey(
        user.id,
        params.organization_id,
        params.workspace_id,
        params.api_key_id,
      );
      return context.body(null, 204);
    } catch (error) {
      return controlError(context, error);
    }
  });
}

function unauthenticated(context: Parameters<typeof problemDocument>[0]) {
  return context.json(
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
}
