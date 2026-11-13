import { changedFields } from "@gradiated/analytics";
import {
  ApiKeyListSchema,
  CredentialIdentitySchema,
  OAuthWorkspaceSelectionSchema,
  ApiKeyPathSchema,
  ApiKeySchema,
  CreateApiKeySchema,
  CreateWorkspaceSchema,
  UpdateWorkspaceSchema,
  CreatedApiKeySchema,
  OrganizationIdParamsSchema,
  PlaygroundCredentialSchema,
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

import { bearerCredential } from "../auth/workspace-credential.js";
import { consoleOnly } from "../http/audience.js";
import { ApiProblem, problems, requireUser } from "../http/problems.js";
import type { ApiEnvironment } from "../types.js";
import { apiKeyResponse } from "./api-key-response.js";

const updateWorkspaceRoute = createRoute({
  method: "patch",
  path: "/api/v1/workspaces/{workspace_id}",
  operationId: "updateWorkspace",
  summary: "Update workspace",
  description: "Changes the workspace's settings.",
  tags: ["Workspaces"],
  request: {
    params: WorkspacePathSchema,
    body: {
      required: true,
      content: { "application/json": { schema: UpdateWorkspaceSchema } },
    },
  },
  responses: {
    200: {
      description:
        "Updated workspace settings. Retention applies to new captures.",
      content: { "application/json": { schema: WorkspaceSchema } },
    },
    401: { description: "Authentication required.", content: problemContent },
    403: {
      description: "Workspace management denied.",
      content: problemContent,
    },
    404: { description: "Workspace not found.", content: problemContent },
    409: {
      description: "A workspace with this name already exists.",
      content: problemContent,
    },
    422: { description: "Invalid workspace update.", content: problemContent },
  },
});
const archiveWorkspaceRoute = createRoute({
  method: "delete",
  path: "/api/v1/workspaces/{workspace_id}",
  operationId: "deleteWorkspace",
  summary: "Archive workspace",
  description: "Archives a workspace.",
  tags: ["Workspaces"],
  request: { params: WorkspacePathSchema },
  responses: {
    202: {
      description:
        "Workspace archived. Content deletion will be retried until complete.",
    },
    401: { description: "Authentication required.", content: problemContent },
    403: {
      description: "Workspace management denied.",
      content: problemContent,
    },
    404: { description: "Workspace not found.", content: problemContent },
    409: {
      description: "A workspace with this name already exists.",
      content: problemContent,
    },
    422: { description: "Invalid workspace update.", content: problemContent },
  },
});
const listWorkspacesRoute = createRoute({
  method: "get",
  path: "/api/v1/organizations/{organization_id}/workspaces",
  operationId: "listWorkspaces",
  summary: "List workspaces",
  description: "Lists the organization's workspaces.",
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
  summary: "Create workspace",
  description: "Creates a workspace.",
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

const getCurrentCredentialRoute = createRoute({
  method: "get",
  path: "/api/v1/credentials/current",
  operationId: "getCurrentCredential",
  summary: "Get current credential",
  description:
    "Identifies the workspace API key or OAuth access token in the Authorization or x-api-key header.",
  tags: ["API keys"],
  security: [{ InferenceBearer: [] }, { InferenceApiKey: [] }],
  responses: {
    200: {
      description: "The credential's organization and workspace.",
      content: { "application/json": { schema: CredentialIdentitySchema } },
    },
    401: {
      description: "The credential is missing, unknown, expired or revoked.",
      content: problemContent,
    },
  },
});

const createCredentialInferenceKeyRoute = createRoute({
  method: "post",
  path: "/api/v1/credentials/current/inference-keys",
  operationId: "createCredentialInferenceKey",
  summary: "Create inference key for OAuth token",
  description:
    "Exchanges the OAuth access token in the Authorization header for a one-hour inference key of its member's in its workspace. Inference takes only API keys. Each call rotates the member's key for that OAuth client, which is not listed with the workspace keys; other clients' keys are unaffected.",
  tags: ["API keys"],
  security: [{ InferenceBearer: [] }],
  responses: {
    201: {
      description: "A one-hour inference key.",
      headers: {
        "Cache-Control": {
          description: "Prevents storage of the one-time secret.",
          schema: { type: "string" },
        },
      },
      content: { "application/json": { schema: PlaygroundCredentialSchema } },
    },
    401: {
      description: "The credential is missing, unknown, expired or revoked.",
      content: problemContent,
    },
    403: {
      description:
        "The credential is an API key, or the workspace cannot be used.",
      content: problemContent,
    },
  },
});

const selectOAuthWorkspaceRoute = createRoute({
  ...consoleOnly,
  method: "put",
  path: "/api/v1/me/oauth-workspace",
  operationId: "selectOAuthWorkspace",
  summary: "Select OAuth workspace",
  description:
    "Chooses the workspace that the OAuth consent being given in this browser session grants a client.",
  tags: ["Session"],
  request: {
    body: {
      required: true,
      content: {
        "application/json": { schema: OAuthWorkspaceSelectionSchema },
      },
    },
  },
  responses: {
    204: { description: "The workspace is selected for this session." },
    401: {
      description: "No browser session is present.",
      content: problemContent,
    },
    403: {
      description: "The workspace is archived or its organization suspended.",
      content: problemContent,
    },
    404: {
      description: "The workspace was not found.",
      content: problemContent,
    },
  },
});

const listApiKeysRoute = createRoute({
  method: "get",
  path: "/api/v1/workspaces/{workspace_id}/api-keys",
  operationId: "listApiKeys",
  summary: "List API keys",
  description: "Lists the workspace's API keys.",
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
  path: "/api/v1/workspaces/{workspace_id}/api-keys",
  operationId: "createApiKey",
  summary: "Create API key",
  description: "Creates an API key for inference.",
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

const createPlaygroundCredentialRoute = createRoute({
  method: "post",
  path: "/api/v1/workspaces/{workspace_id}/playground-credentials",
  operationId: "createPlaygroundCredential",
  tags: ["API keys"],
  request: { params: WorkspacePathSchema },
  responses: {
    201: {
      description:
        "A one-hour inference key for the console playground. Each call rotates the member's single playground key, which is not listed with the workspace keys.",
      headers: {
        "Cache-Control": {
          description: "Prevents storage of the one-time secret.",
          schema: { type: "string" },
        },
      },
      content: { "application/json": { schema: PlaygroundCredentialSchema } },
    },
    401: {
      description: "Authentication is required.",
      content: problemContent,
    },
    403: {
      description: "The workspace cannot be used.",
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

const revokeApiKeyRoute = createRoute({
  method: "delete",
  path: "/api/v1/workspaces/{workspace_id}/api-keys/{api_key_id}",
  operationId: "revokeApiKey",
  summary: "Revoke API key",
  description: "Revokes an API key.",
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
  trace_capture_enabled: record.traceCaptureEnabled,
  trace_retention_days: record.traceRetentionDays as 30 | 90 | 180,
  default_judge_model: record.defaultJudgeModel,
  archived_at: record.archivedAt?.toISOString() ?? null,
  created_at: record.createdAt.toISOString(),
  updated_at: record.updatedAt.toISOString(),
});

export const registerWorkspaceRoutes = (
  app: OpenAPIHono<ApiEnvironment>,
  workspaces: WorkspaceApiKeyService,
): void => {
  app.openapi(updateWorkspaceRoute, async (c) => {
    const user = await requireUser(c);
    const p = c.req.valid("param");
    const workspace = await workspaces.updateWorkspace(
      user.id,
      p.workspace_id,
      c.req.valid("json"),
    );
    c.get("analytics")?.track(user.id, "workspace_settings_updated", {
      organization_id: workspace.organizationId,
      workspace_id: workspace.id,
      changed_fields: changedFields(c.req.valid("json")),
    });

    return c.json(workspaceResponse(workspace), 200);
  });
  app.openapi(archiveWorkspaceRoute, async (c) => {
    const user = await requireUser(c);
    const p = c.req.valid("param");
    await workspaces.archiveWorkspace(user.id, p.workspace_id);
    c.get("analytics")?.trackWorkspace(user.id, "workspace_archived", {
      workspace_id: p.workspace_id,
    });

    return c.body(null, 202);
  });
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

    context.get("analytics")?.track(user.id, "workspace_created", {
      organization_id: workspace.organizationId,
      workspace_id: workspace.id,
      is_default: workspace.isDefault,
    });

    context.set("logResourceIds", { workspace_id: workspace.id });
    return context.json(workspaceResponse(workspace), 201);
  });

  app.openapi(getCurrentCredentialRoute, async (context) => {
    const secret = bearerCredential(context.req.raw.headers);
    const owner = secret && (await workspaces.describeCredential(secret));
    if (!owner) throw new ApiProblem(problems.unauthenticated);

    return context.json(
      {
        type: owner.credential,
        id: owner.credentialId,
        organization_id: owner.organizationId,
        workspace_id: owner.workspaceId,
        workspace_name: owner.workspaceName,
        organization_name: owner.organizationName,
        organization_slug: owner.organizationSlug,
        user: {
          id: owner.user.id,
          name: owner.user.name,
          email: owner.user.email,
        },
      },
      200,
    );
  });

  app.openapi(createCredentialInferenceKeyRoute, async (context) => {
    const secret = bearerCredential(context.req.raw.headers);
    const owner = secret && (await workspaces.authenticateCredential(secret));
    if (!secret || !owner) throw new ApiProblem(problems.unauthenticated);
    if (owner.credential !== "oauth_token")
      throw new ApiProblem(
        problems.forbidden("API keys call inference with themselves."),
      );

    const credential = await workspaces.createOAuthInferenceCredential(secret);
    if (!credential) throw new ApiProblem(problems.unauthenticated);

    context.set("logResourceIds", { api_key_id: credential.apiKeyId });
    context.header("Cache-Control", "no-store");
    return context.json(
      {
        secret: credential.secret,
        expires_at: credential.expiresAt.toISOString(),
      },
      201,
    );
  });

  app.openapi(selectOAuthWorkspaceRoute, async (context) => {
    const user = await requireUser(context);
    if (!user.sessionId) throw new ApiProblem(problems.unauthenticated);

    const { workspace_id } = context.req.valid("json");
    await workspaces.selectOAuthWorkspace(
      user.id,
      user.sessionId,
      workspace_id,
    );

    return context.body(null, 204);
  });

  app.openapi(listApiKeysRoute, async (context) => {
    const user = await requireUser(context);
    const params = context.req.valid("param");
    const rows = await workspaces.listApiKeys(user.id, params.workspace_id);

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
      params.workspace_id,
      {
        name: input.name,
        expiresAt: input.expires_at ? new Date(input.expires_at) : null,
      },
    );

    context.get("analytics")?.track(user.id, "api_key_created", {
      organization_id: created.apiKey.organizationId,
      workspace_id: created.apiKey.workspaceId,
      api_key_id: created.apiKey.id,
      has_expiry: created.apiKey.expiresAt !== null,
    });

    context.set("logResourceIds", { api_key_id: created.apiKey.id });
    context.header("Cache-Control", "no-store");
    return context.json(
      { api_key: apiKeyResponse(created.apiKey), secret: created.secret },
      201,
    );
  });

  app.openapi(createPlaygroundCredentialRoute, async (context) => {
    const user = await requireUser(context);
    const params = context.req.valid("param");
    const credential = await workspaces.createPlaygroundCredential(
      user.id,
      params.workspace_id,
    );

    context.set("logResourceIds", { api_key_id: credential.apiKeyId });
    context.header("Cache-Control", "no-store");
    return context.json(
      {
        secret: credential.secret,
        expires_at: credential.expiresAt.toISOString(),
      },
      201,
    );
  });

  app.openapi(revokeApiKeyRoute, async (context) => {
    const user = await requireUser(context);
    const params = context.req.valid("param");
    await workspaces.revokeApiKey(
      user.id,
      params.workspace_id,
      params.api_key_id,
    );

    context.get("analytics")?.trackWorkspace(user.id, "api_key_revoked", {
      workspace_id: params.workspace_id,
      api_key_id: params.api_key_id,
    });

    return context.body(null, 204);
  });
};
