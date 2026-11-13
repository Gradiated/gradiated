import { z } from "zod";
import {
  GatewayModelDeploymentSchema,
  ModelPropertiesSchema,
  ModelSchema,
  OpenRouterModelIdSchema,
  UuidSchema,
} from "@gradiated/contracts";
import { MODEL_STATUSES } from "../db/schema/index.js";

export const ModelRecordSchema = z.object({
  id: ModelSchema.shape.id,
  aliases: z
    .array(ModelSchema.shape.id.regex(/^[a-z0-9][a-z0-9._/-]*$/))
    .default([]),
  name: ModelSchema.shape.name,
  status: z.enum(MODEL_STATUSES),
  properties: ModelPropertiesSchema,
  openrouterModelId: OpenRouterModelIdSchema.nullable(),
  tokenizerPath: z.string().min(1).max(300).nullable(),
  tokenizerRevision: z
    .string()
    .regex(/^[0-9a-f]{40}$/)
    .nullable(),
  createdAt: z.date(),
  updatedAt: z.date(),
});

export const ModelDeploymentRecordSchema = z.object({
  id: GatewayModelDeploymentSchema.shape.id,
  modelId: ModelSchema.shape.id,
  status: GatewayModelDeploymentSchema.shape.status,
  provider: GatewayModelDeploymentSchema.shape.provider,
  region: GatewayModelDeploymentSchema.shape.region,
  faultDomain: GatewayModelDeploymentSchema.shape.fault_domain,
  serviceUrl: GatewayModelDeploymentSchema.shape.service_url,
  release: GatewayModelDeploymentSchema.shape.release,
  createdAt: z.date(),
  updatedAt: z.date(),
});

export const ModelDeploymentInsertSchema = ModelDeploymentRecordSchema.omit({
  createdAt: true,
  updatedAt: true,
}).extend({ instanceId: UuidSchema.nullable().optional() });

export type ModelRecord = z.infer<typeof ModelRecordSchema>;
export type ModelDeploymentRecord = z.infer<typeof ModelDeploymentRecordSchema>;
