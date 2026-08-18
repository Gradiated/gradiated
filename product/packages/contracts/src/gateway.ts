import { z } from "@hono/zod-openapi";

import { TimestampSchema, UuidSchema } from "./common.js";
import { ModelPropertiesSchema } from "./models.js";

const BoundedIdentifierSchema = z.string().min(1).max(300);

export const GatewayAccountSchema = z
  .strictObject({
    organization_id: UuidSchema,
    organization_kind: z.enum(["customer", "distribution_channel"]),
    organization_status: z.enum(["active", "suspended"]),
    billing_mode: z.enum(["prepaid", "invoiced"]),
    balance: z.string().regex(/^-?\d+$/),
  })
  .openapi("GatewayAccount");

export const GatewayWorkspaceSchema = z
  .strictObject({
    organization_id: UuidSchema,
    workspace_id: UuidSchema,
    archived_at: TimestampSchema.nullable(),
  })
  .openapi("GatewayWorkspace");

export const GatewayCredentialSchema = z
  .strictObject({
    api_key_id: UuidSchema,
    organization_id: UuidSchema,
    workspace_id: UuidSchema,
    expires_at: TimestampSchema.nullable(),
    revoked_at: TimestampSchema.nullable(),
  })
  .openapi("GatewayCredential");

export const ModelDeploymentReleaseSchema = z
  .strictObject({
    schema_version: z.literal(1),
    runtime_revision: BoundedIdentifierSchema,
    model_path: BoundedIdentifierSchema,
    model_revision: BoundedIdentifierSchema,
    tokenizer_path: BoundedIdentifierSchema,
    tokenizer_revision: BoundedIdentifierSchema,
  })
  .openapi("ModelDeploymentRelease");

export const GatewayModelDeploymentSchema = z
  .strictObject({
    id: UuidSchema,
    status: z.enum(["available", "unavailable", "draining"]),
    service_url: z
      .url()
      .max(2_048)
      .refine(
        (value) => value.startsWith("http://") || value.startsWith("https://"),
      ),
    release: ModelDeploymentReleaseSchema,
  })
  .openapi("GatewayModelDeployment");

export const GatewayModelSchema = z
  .strictObject({
    id: z.string().min(1).max(200),
    name: z.string().min(1).max(200),
    status: z.enum(["available", "unavailable", "retired"]),
    properties: ModelPropertiesSchema,
    deployments: z.array(GatewayModelDeploymentSchema),
  })
  .openapi("GatewayModel");

export const GenerationPriceComponentSchema = z.strictObject({
  unit: z.enum([
    "request",
    "input_token",
    "cached_input_token",
    "output_token",
    "reasoning_token",
  ]),
  quantity: z.number().int().nonnegative(),
  unit_price: z.number().int().nonnegative(),
  amount: z.number().int().nonnegative(),
});

export const GenerationPropertiesSchema = z
  .strictObject({
    event_schema_version: z.literal(1),
    external_id: z.string().max(300).nullable(),
    organization_id: UuidSchema,
    workspace_id: UuidSchema,
    api_key_id: UuidSchema,
    model_id: z.string().min(1).max(200),
    served_release_digest: z.string().regex(/^sha256:[a-f0-9]{64}$/),
    status: z.enum(["succeeded", "failed", "cancelled", "abandoned"]),
    streamed: z.boolean(),
    pricing: z.strictObject({
      schema_version: z.literal(1),
      components: z.array(GenerationPriceComponentSchema),
    }),
    usage: z.strictObject({
      charge: z.number().int().nonnegative(),
      input_tokens: z.number().int().nonnegative(),
      cached_input_tokens: z.number().int().nonnegative(),
      output_tokens: z.number().int().nonnegative(),
      reasoning_tokens: z.number().int().nonnegative(),
    }),
    outcome: z.strictObject({
      finish_reason: z.string().max(100).nullable(),
      error_code: z.string().max(100).nullable(),
      usable_output_delivered: z.boolean(),
      cancellation_owner: z.enum(["client", "server", "runtime"]).nullable(),
    }),
    timing: z.strictObject({
      received_at: TimestampSchema,
      started_at: TimestampSchema.nullable(),
      first_token_at: TimestampSchema.nullable(),
      completed_at: TimestampSchema,
    }),
  })
  .openapi("GenerationProperties");

export const GenerationSettledSchema = z
  .strictObject({
    generation_id: UuidSchema,
    properties: GenerationPropertiesSchema,
  })
  .openapi("GenerationSettled");

export type GatewayAccount = z.infer<typeof GatewayAccountSchema>;
export type GatewayCredential = z.infer<typeof GatewayCredentialSchema>;
export type GatewayModel = z.infer<typeof GatewayModelSchema>;
export type GatewayModelDeployment = z.infer<
  typeof GatewayModelDeploymentSchema
>;
export type GatewayWorkspace = z.infer<typeof GatewayWorkspaceSchema>;
export type GenerationProperties = z.infer<typeof GenerationPropertiesSchema>;
export type GenerationSettled = z.infer<typeof GenerationSettledSchema>;
export type ModelDeploymentRelease = z.infer<
  typeof ModelDeploymentReleaseSchema
>;
