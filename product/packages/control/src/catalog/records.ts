import { z } from "zod";
import {
  GatewayModelDeploymentSchema,
  ModelPropertiesSchema,
  ModelSchema,
  UuidSchema,
} from "@gradiated/contracts";
import { MODEL_STATUSES } from "../db/schema/index.js";

export const ModelRecordSchema = z.object({
  id: ModelSchema.shape.id,
  name: ModelSchema.shape.name,
  status: z.enum(MODEL_STATUSES),
  properties: ModelPropertiesSchema,
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
