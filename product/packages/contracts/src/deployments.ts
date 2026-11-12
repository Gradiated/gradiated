import { z } from "@hono/zod-openapi";

import {
  BoundedIdentifierSchema,
  SnakeCaseCodeSchema,
  DeploymentIdSchema,
} from "./common.js";

export const ModelDeploymentReleaseSchema = z
  .strictObject({
    schema_version: z.literal(1),
    runtime_revision: BoundedIdentifierSchema,
    protocol: z
      .enum(["system_one"])
      .optional()
      .describe(
        "Absent means the OpenAI chat protocol, which every ordinary LLM deployment serves.",
      ),
    model_path: BoundedIdentifierSchema,
    model_revision: BoundedIdentifierSchema,
    runtime_model_name: BoundedIdentifierSchema.optional(),
    tokenizer_path: BoundedIdentifierSchema,
    tokenizer_revision: BoundedIdentifierSchema,
    tokenizer_mode: z.enum(["deepseek_v4", "deepseek_v41"]).optional(),
    lora_enabled: z.boolean().optional(),
    lora_base_model_revision: BoundedIdentifierSchema.optional().describe(
      "Qualified training checkpoint revision accepted by this deployment; defaults to model_revision.",
    ),
  })
  .openapi("ModelDeploymentRelease");

export const GatewayModelDeploymentSchema = z
  .strictObject({
    id: DeploymentIdSchema,
    status: z.enum(["available", "unavailable", "draining"]),
    provider: z
      .string()
      .min(1)
      .max(100)
      .regex(/^[a-z][a-z0-9_-]*$/),
    region: z.string().min(1).max(100),
    fault_domain: z.string().min(1).max(300),
    service_url: z.url({ protocol: /^https?$/ }).max(2_048),
    release: ModelDeploymentReleaseSchema,
  })
  .openapi("GatewayModelDeployment");

// The deployment status report crosses independently deployed processes.
// Unknown fields are ignored so a newer runtime cannot break ingest.
export const DeploymentStatusReportSchema = z
  .object({
    schema_version: z.literal(1),
    deployment_id: DeploymentIdSchema,
    runtime_revision: BoundedIdentifierSchema,
    healthy: z.boolean(),
    accepting_requests: z.boolean(),
    // The runtime's concurrent request limit. The gateway weights routing by it
    // and routes with equal weights when any candidate leaves it out.
    active_requests: z.number().int().min(1).max(4_096).optional(),
    reason_code: SnakeCaseCodeSchema.min(1).max(100).nullable(),
  })
  .openapi("DeploymentStatusReport");

export type DeploymentStatusReport = z.infer<
  typeof DeploymentStatusReportSchema
>;
export type GatewayModelDeployment = z.infer<
  typeof GatewayModelDeploymentSchema
>;
export type ModelDeploymentRelease = z.infer<
  typeof ModelDeploymentReleaseSchema
>;
