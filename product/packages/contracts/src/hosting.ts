import { z } from "@hono/zod-openapi";
import { ModelIdSchema, UuidSchema } from "./common.js";
import { ModelDeploymentReleaseSchema } from "./deployments.js";

export const LoraProfileSchema = z
  .strictObject({
    id: z.string().regex(/^[a-z0-9-]{1,64}$/),
    base_model_id: ModelIdSchema,
    release: ModelDeploymentReleaseSchema,
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
    gpu_slots: z.number().int().min(1).max(1024),
    max_adapters: z.number().int().min(1).max(1024),
    cpu_cache_bytes: z.number().int().positive().safe(),
    disk_cache_bytes: z.number().int().positive().safe(),
    max_concurrency: z.number().int().min(1).max(1024),
  })
  .refine((profile) => profile.gpu_slots <= profile.max_adapters, {
    path: ["gpu_slots"],
    message: "GPU slots cannot exceed CPU adapter capacity",
  })
  .openapi("LoraProfile");
export type LoraProfile = z.infer<typeof LoraProfileSchema>;

export const RuntimeAdapterSchema = z
  .strictObject({
    version_id: UuidSchema,
    sha256: z.string().regex(/^[a-f0-9]{64}$/),
    name: z.string().regex(/^ft-[a-f0-9-]{36}-[a-f0-9]{64}$/),
    profile_id: LoraProfileSchema.shape.id,
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
    profile: LoraProfileSchema,
    base_model_revision: z.string().min(1).max(300),
    size_bytes: z.number().int().positive().safe(),
    rank: z.number().int().positive().max(64),
    download_url: z.url({ protocol: /^https$/ }),
  })
  .refine(
    (preparation) => preparation.adapter.profile_id === preparation.profile.id,
    {
      path: ["adapter", "profile_id"],
      message: "Adapter profile must match the serving profile",
    },
  )
  .refine((preparation) => preparation.rank <= preparation.profile.max_rank, {
    path: ["rank"],
    message: "Adapter rank exceeds the serving profile limit",
  })
  .refine(
    (preparation) =>
      preparation.base_model_revision ===
      preparation.profile.release.model_revision,
    {
      path: ["base_model_revision"],
      message: "Adapter base revision must match the serving release",
    },
  )
  .openapi("AdapterPreparation");

export const adapterRuntimeName = (versionId: string, sha256: string): string =>
  RuntimeAdapterSchema.shape.name.parse(
    `ft-${UuidSchema.parse(versionId)}-${sha256}`,
  );
