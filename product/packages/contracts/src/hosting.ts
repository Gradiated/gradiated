import { z } from "@hono/zod-openapi";
import { ModelIdSchema, UuidSchema } from "./common.js";
import { ModelDeploymentReleaseSchema } from "./deployments.js";

export const LoraHostConfigSchema = z
  .strictObject({
    id: z.string().regex(/^[a-z0-9-]{1,64}$/),
    base_model_id: ModelIdSchema,
    release: ModelDeploymentReleaseSchema,
    tensor_parallel_size: z.number().int().positive().safe(),
    max_rank: z.union([
      z.literal(8),
      z.literal(16),
      z.literal(32),
      z.literal(64),
    ]),
    target_modules: z.array(z.string().min(1)).min(1),
    layer_count: z.number().int().positive().safe(),
    gpu_slots: z.number().int().positive().safe(),
    cpu_adapter_slots: z.number().int().positive().safe(),
    cpu_cache_bytes: z.number().int().positive().safe(),
    disk_cache_bytes: z.number().int().positive().safe(),
    max_concurrency: z.number().int().positive().safe(),
  })
  .refine((config) => config.gpu_slots <= config.cpu_adapter_slots, {
    path: ["gpu_slots"],
    message: "GPU slots cannot exceed CPU adapter capacity",
  })
  .openapi("LoraHostConfig");
export type LoraHostConfig = z.infer<typeof LoraHostConfigSchema>;

export const RuntimeAdapterSchema = z
  .strictObject({
    version_id: UuidSchema,
    sha256: z.string().regex(/^[a-f0-9]{64}$/),
    name: z.string().regex(/^ft-[a-f0-9-]{36}-[a-f0-9]{64}$/),
  })
  .refine(
    (adapter) => adapter.name === `ft-${adapter.version_id}-${adapter.sha256}`,
    {
      path: ["name"],
      message: "Name must match the immutable adapter identity",
    },
  )
  .openapi("RuntimeAdapter");

export const AdapterPreparationSchema = z
  .strictObject({
    workspace_id: UuidSchema,
    adapter: RuntimeAdapterSchema,
    base_model_id: ModelIdSchema,
    base_model_revision: z.string().min(1).max(300),
    size_bytes: z.number().int().positive().safe(),
    rank: z.number().int().positive().safe(),
    download_url: z.url({ protocol: /^https$/ }),
  })
  .openapi("AdapterPreparation");

export const adapterRuntimeName = (versionId: string, sha256: string): string =>
  RuntimeAdapterSchema.shape.name.parse(
    `ft-${UuidSchema.parse(versionId)}-${sha256}`,
  );
