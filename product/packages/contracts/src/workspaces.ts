import { z } from "@hono/zod-openapi";

import { TimestampSchema, UuidSchema } from "./common.js";

export const WorkspaceSchema = z
  .object({
    id: UuidSchema,
    organization_id: UuidSchema,
    name: z.string().min(1).max(200),
    is_default: z.boolean(),
    archived_at: TimestampSchema.nullable(),
    created_at: TimestampSchema,
    updated_at: TimestampSchema,
  })
  .openapi("Workspace");

export const CreateWorkspaceSchema = z
  .strictObject({
    name: z.string().trim().min(1).max(200),
  })
  .openapi("CreateWorkspace");

export const WorkspaceListSchema = z
  .object({
    data: z.array(WorkspaceSchema),
    next_cursor: z.string().nullable(),
  })
  .openapi("WorkspaceList");

export const ApiKeySchema = z
  .object({
    id: UuidSchema,
    organization_id: UuidSchema,
    workspace_id: UuidSchema,
    name: z.string().min(1).max(200),
    expires_at: TimestampSchema.nullable(),
    revoked_at: TimestampSchema.nullable(),
    created_by: UuidSchema.nullable(),
    created_at: TimestampSchema,
    updated_at: TimestampSchema,
  })
  .openapi("ApiKey");

export const ApiKeyListSchema = z
  .object({
    data: z.array(ApiKeySchema),
    next_cursor: z.string().nullable(),
  })
  .openapi("ApiKeyList");

export const CreateApiKeySchema = z
  .strictObject({
    name: z.string().trim().min(1).max(200),
    expires_at: TimestampSchema.nullable().optional(),
  })
  .openapi("CreateApiKey");

export const CreatedApiKeySchema = z
  .object({
    api_key: ApiKeySchema,
    secret: z.string().regex(/^grad_[A-Za-z0-9_-]{43}$/),
  })
  .openapi("CreatedApiKey");

export const WorkspacePathSchema = z.object({
  organization_id: UuidSchema,
  workspace_id: UuidSchema,
});

export const ApiKeyPathSchema = WorkspacePathSchema.extend({
  api_key_id: UuidSchema,
});

export const WorkspaceListQuerySchema = z.object({
  include_archived: z.enum(["true", "false"]).optional(),
});

export type ApiKey = z.infer<typeof ApiKeySchema>;
export type CreatedApiKeyResponse = z.infer<typeof CreatedApiKeySchema>;
export type CreateWorkspace = z.infer<typeof CreateWorkspaceSchema>;
export type Workspace = z.infer<typeof WorkspaceSchema>;
