import { z } from "@hono/zod-openapi";

import { EvaluationJudgeSchema } from "./training.js";
import {
  ApiKeySecretSchema,
  NameInputSchema,
  NameSchema,
  pageFields,
  TimestampSchema,
  UuidSchema,
} from "./common.js";

export const WorkspaceSchema = z
  .object({
    id: UuidSchema,
    organization_id: UuidSchema,
    name: NameSchema,
    is_default: z.boolean(),
    trace_capture_enabled: z
      .boolean()
      .describe("Whether task-labelled requests are captured."),
    trace_retention_days: z.union([
      z.literal(30),
      z.literal(90),
      z.literal(180),
    ]),
    default_judge_model: EvaluationJudgeSchema,
    archived_at: TimestampSchema.nullable(),
    created_at: TimestampSchema,
    updated_at: TimestampSchema,
  })
  .openapi("Workspace");

export const CreateWorkspaceSchema = z
  .strictObject({
    name: NameInputSchema,
  })
  .openapi("CreateWorkspace");

export const UpdateWorkspaceSchema = WorkspaceSchema.pick({
  trace_capture_enabled: true,
  trace_retention_days: true,
  default_judge_model: true,
})
  .extend({ name: NameInputSchema })
  .partial()
  .strict()
  .refine(
    (input) => Object.keys(input).length > 0,
    "Provide at least one workspace field.",
  )
  .openapi("UpdateWorkspace");
export type UpdateWorkspace = z.infer<typeof UpdateWorkspaceSchema>;

export const WorkspaceListSchema = z
  .object(pageFields(WorkspaceSchema))
  .openapi("WorkspaceList");

export const ApiKeySchema = z
  .object({
    id: UuidSchema,
    organization_id: UuidSchema,
    workspace_id: UuidSchema,
    name: NameSchema,
    expires_at: TimestampSchema.nullable(),
    revoked_at: TimestampSchema.nullable(),
    created_by: UuidSchema.nullable(),
    created_at: TimestampSchema,
    updated_at: TimestampSchema,
  })
  .openapi("ApiKey");

export const ApiKeyListSchema = z
  .object(pageFields(ApiKeySchema))
  .openapi("ApiKeyList");

export const CreateApiKeySchema = z
  .strictObject({
    name: NameInputSchema,
    expires_at: TimestampSchema.nullable().optional(),
  })
  .openapi("CreateApiKey");

export const CreatedApiKeySchema = z
  .object({
    api_key: ApiKeySchema,
    secret: ApiKeySecretSchema,
  })
  .openapi("CreatedApiKey");

export const PlaygroundCredentialSchema = z
  .object({
    secret: ApiKeySecretSchema,
    expires_at: TimestampSchema,
  })
  .openapi("PlaygroundCredential");

export const WorkspacePathSchema = z.object({
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
export type PlaygroundCredential = z.infer<typeof PlaygroundCredentialSchema>;
export type CreateWorkspace = z.infer<typeof CreateWorkspaceSchema>;
export type Workspace = z.infer<typeof WorkspaceSchema>;
