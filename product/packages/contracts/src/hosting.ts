import { z } from "@hono/zod-openapi";
import { ModelDeploymentReleaseSchema } from "./deployments.js";
import { ModelPropertiesSchema } from "./models.js";
import { ModelIdSchema, TimestampSchema, UuidSchema } from "./common.js";

export const LoraProfileSchema = z
  .strictObject({
    id: z.string().regex(/^[a-z0-9-]{1,64}$/),
    base_model_id: ModelIdSchema,
    release: ModelDeploymentReleaseSchema,
    properties: ModelPropertiesSchema,
    tensor_parallel_size: z.number().int().min(1).max(8),
    max_rank: z.union([
      z.literal(8),
      z.literal(16),
      z.literal(32),
      z.literal(64),
    ]),
    target_modules: z
      .array(z.string().regex(/^[a-zA-Z0-9_]+$/))
      .min(1)
      .max(64),
    layer_count: z.number().int().positive().max(256),
    max_adapters: z.number().int().min(1).max(1024),
    cache_bytes: z.number().int().positive().safe(),
    max_concurrency: z.number().int().min(1).max(1024),
  })
  .openapi("LoraProfile");
export type LoraProfile = z.infer<typeof LoraProfileSchema>;

export const HostVersionSchema = z
  .strictObject({
    profile_id: LoraProfileSchema.shape.id,
  })
  .openapi("HostVersion");

export const VersionHostingSchema = z
  .strictObject({
    version_id: UuidSchema,
    desired: z.enum(["hosted", "unhosted"]),
    revision: z.number().int().positive(),
    profile_id: LoraProfileSchema.shape.id,
    stage: z.enum(["pending", "ready", "failed", "draining", "unhosted"]),
    error_code: z
      .enum(["preparation_failed", "capacity_unavailable"])
      .nullable(),
    updated_at: TimestampSchema,
  })
  .openapi("VersionHosting");

export const RuntimeAdapterSchema = z
  .strictObject({
    version_id: UuidSchema,
    sha256: z.string().regex(/^[a-f0-9]{64}$/),
    name: z.string().regex(/^ft-[a-f0-9-]{36}-[a-f0-9]{64}$/),
    profile_id: LoraProfileSchema.shape.id,
  })
  .openapi("RuntimeAdapter");

export const AdapterPreparationSchema = z
  .strictObject({
    adapter: RuntimeAdapterSchema,
    profile: LoraProfileSchema,
    size_bytes: z.number().int().positive().safe(),
    rank: z.number().int().positive().max(64),
    download_url: z.url({ protocol: /^https$/ }),
  })
  .openapi("AdapterPreparation");

export const adapterRuntimeName = (versionId: string, sha256: string): string =>
  RuntimeAdapterSchema.shape.name.parse(
    `ft-${UuidSchema.parse(versionId)}-${sha256}`,
  );
