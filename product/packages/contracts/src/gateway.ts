import { z } from "@hono/zod-openapi";

import { TimestampSchema, UuidSchema } from "./common.js";
import { ModelPropertiesSchema } from "./models.js";
import { ServiceTierSchema } from "./service-tiers.js";

const BoundedIdentifierSchema = z.string().min(1).max(300);

export const ChatCompletionRequestSchema = z
  .object({
    model: z.string().min(1).max(200),
    messages: z.array(z.unknown()).min(1),
    stream: z.boolean().default(false),
    service_tier: ServiceTierSchema.default("default"),
    session_id: z.string().min(1).max(256).optional(),
    max_completion_tokens: z.number().int().positive().optional(),
    max_tokens: z.number().int().positive().optional(),
  })
  .catchall(z.unknown())
  .superRefine((request, context) => {
    if (
      request.max_completion_tokens !== undefined &&
      request.max_tokens !== undefined
    ) {
      context.addIssue({
        code: "custom",
        message: "max_completion_tokens and max_tokens cannot both be provided",
        path: ["max_completion_tokens"],
      });
    }
  })
  .openapi("ChatCompletionRequest");

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
    runtime_model_name: BoundedIdentifierSchema.optional(),
    tokenizer_path: BoundedIdentifierSchema,
    tokenizer_revision: BoundedIdentifierSchema,
    tokenizer_mode: z.enum(["deepseek_v4"]).optional(),
  })
  .openapi("ModelDeploymentRelease");

export const GatewayModelDeploymentSchema = z
  .strictObject({
    id: UuidSchema,
    status: z.enum(["available", "unavailable", "draining"]),
    provider: z
      .string()
      .min(1)
      .max(100)
      .regex(/^[a-z][a-z0-9_-]*$/),
    region: z.string().min(1).max(100),
    fault_domain: z.string().min(1).max(300),
    service_url: z
      .url()
      .max(2_048)
      .refine(
        (value) => value.startsWith("http://") || value.startsWith("https://"),
      ),
    release: ModelDeploymentReleaseSchema,
  })
  .openapi("GatewayModelDeployment");

export const DeploymentStatusReportSchema = z
  .strictObject({
    schema_version: z.literal(1),
    deployment_id: UuidSchema,
    runtime_revision: BoundedIdentifierSchema,
    healthy: z.boolean(),
    accepting_requests: z.boolean(),
    maximum_concurrency: z.number().int().min(1).max(100_000),
    reason_code: z
      .string()
      .min(1)
      .max(100)
      .regex(/^[a-z][a-z0-9_]*$/)
      .nullable(),
  })
  .openapi("DeploymentStatusReport");

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
    "cache_write_token",
    "output_token",
    "reasoning_token",
  ]),
  quantity: z.number().int().nonnegative(),
  unit_price: z.number().int().nonnegative(),
  amount: z.number().int().nonnegative(),
});

export const GenerationPropertiesSchema = z
  .strictObject({
    event_schema_version: z.union([z.literal(1), z.literal(2)]),
    service_tier: ServiceTierSchema.optional(),
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
      cache_write_tokens: z.number().int().nonnegative(),
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
  .superRefine((properties, context) => {
    if (
      (properties.event_schema_version === 1 &&
        properties.service_tier !== undefined) ||
      (properties.event_schema_version === 2 &&
        properties.service_tier === undefined)
    ) {
      context.addIssue({
        code: "custom",
        message:
          "service_tier must be absent in version 1 and present in version 2",
        path: ["service_tier"],
      });
    }
  })
  .openapi("GenerationProperties");

export const GenerationSettledSchema = z
  .strictObject({
    generation_id: UuidSchema,
    properties: GenerationPropertiesSchema,
  })
  .openapi("GenerationSettled");

export type GatewayAccount = z.infer<typeof GatewayAccountSchema>;
export type ChatCompletionRequest = z.infer<typeof ChatCompletionRequestSchema>;
export type GatewayCredential = z.infer<typeof GatewayCredentialSchema>;
export type DeploymentStatusReport = z.infer<
  typeof DeploymentStatusReportSchema
>;
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
