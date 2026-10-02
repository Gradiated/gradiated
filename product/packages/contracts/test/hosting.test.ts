import { describe, expect, it } from "vitest";
import {
  adapterRuntimeName,
  AdapterPreparationSchema,
  LoraHostConfigSchema,
  RuntimeAdapterSchema,
} from "../src/hosting.js";
import { TaskVersionAdapterSchema } from "../src/training.js";

const versionId = "01980000-0000-7000-8000-000000000001";
const hash = "a".repeat(64);
const hostConfig = {
  id: "tp2",
  base_model_id: "base-model",
  release: {
    schema_version: 1,
    runtime_revision: "runtime-1",
    model_path: "base-model",
    model_revision: "base-revision-1",
    tokenizer_path: "base-model",
    tokenizer_revision: "tokenizer-revision-1",
  },
  tensor_parallel_size: 2,
  max_rank: 8,
  target_modules: ["q_proj", "v_proj"],
  layer_count: 32,
  gpu_slots: 8,
  cpu_adapter_slots: 64,
  cpu_cache_bytes: 8 * 1024 ** 3,
  disk_cache_bytes: 32 * 1024 ** 3,
  max_concurrency: 16,
};
const adapter = {
  version_id: versionId,
  sha256: hash,
  name: adapterRuntimeName(versionId, hash),
};
const preparation = {
  workspace_id: "01980000-0000-7000-8000-000000000002",
  adapter,
  base_model_id: hostConfig.base_model_id,
  base_model_revision: hostConfig.release.model_revision,
  size_bytes: 1024,
  rank: 2,
  download_url: "https://artifacts.example.test/adapter.tar.gz",
};

describe("immutable runtime adapter identity", () => {
  it("keeps different weights and versions in separate runtime namespaces", () => {
    const id = "01980000-0000-7000-8000-000000000001";
    const hash = "a".repeat(64);
    expect(adapterRuntimeName(id, hash)).not.toEqual(
      adapterRuntimeName(id, "b".repeat(64)),
    );
    expect(adapterRuntimeName(id, hash)).not.toEqual(
      adapterRuntimeName(preparation.workspace_id, hash),
    );
    expect(() => adapterRuntimeName(id, "../../adapter")).toThrow();
    expect(
      RuntimeAdapterSchema.safeParse({
        version_id: id,
        sha256: hash,
        name: "public-path",
      }).success,
    ).toBe(false);
  });

  it("rejects a valid runtime name belonging to different weights", () => {
    expect(
      RuntimeAdapterSchema.safeParse({ ...adapter, sha256: "b".repeat(64) })
        .success,
    ).toBe(false);
  });
});

describe("artifact metadata and host cache configuration", () => {
  it("keeps existing training artifacts readable without a recorded base revision", () => {
    const artifact = {
      format: "peft_lora",
      artifact_uri: "s3://artifacts/adapter.tar.gz",
      sha256: hash,
      size_bytes: 1024,
      rank: 2,
    };

    expect(TaskVersionAdapterSchema.parse(artifact)).toEqual(artifact);
    expect(
      TaskVersionAdapterSchema.parse({
        ...artifact,
        base_model_revision: preparation.base_model_revision,
      }).base_model_revision,
    ).toBe(preparation.base_model_revision);
  });

  it("accepts rank-2 adapters with independent CPU and disk budgets", () => {
    expect(AdapterPreparationSchema.parse(preparation)).toEqual(preparation);
  });

  it.each([
    ["too many GPU slots", { gpu_slots: 65 }],
    [
      "an unbounded CPU budget",
      { cpu_cache_bytes: Number.MAX_SAFE_INTEGER + 1 },
    ],
    ["an empty disk budget", { disk_cache_bytes: 0 }],
  ])("rejects %s", (_, overrides) => {
    expect(
      LoraHostConfigSchema.safeParse({ ...hostConfig, ...overrides }).success,
    ).toBe(false);
  });

  it.each([
    ["host configuration", { profile: hostConfig }],
    ["tensor parallelism", { tensor_parallel_size: 4 }],
    ["cache settings", { gpu_slots: 64 }],
    [
      "a serving profile selector",
      { adapter: { ...adapter, profile_id: "tp4" } },
    ],
    [
      "an insecure artifact URL",
      { download_url: "http://artifacts.example.test/adapter.tar.gz" },
    ],
  ])("rejects %s in an adapter preparation request", (_, overrides) => {
    expect(
      AdapterPreparationSchema.safeParse({ ...preparation, ...overrides })
        .success,
    ).toBe(false);
  });

  it("keeps one adapter identity across TP2 and TP4 host configurations", () => {
    const tp2 = LoraHostConfigSchema.parse(hostConfig);
    const tp4 = LoraHostConfigSchema.parse({
      ...hostConfig,
      tensor_parallel_size: 4,
    });

    expect(tp2.tensor_parallel_size).toBe(2);
    expect(tp4.tensor_parallel_size).toBe(4);
    expect(AdapterPreparationSchema.parse(preparation).adapter).toEqual(
      adapter,
    );
  });

  it("leaves architecture geometry to the qualified host configuration", () => {
    expect(
      LoraHostConfigSchema.safeParse({
        ...hostConfig,
        tensor_parallel_size: 16,
        layer_count: 512,
        target_modules: ["attention.q_proj", "experts.gate_proj"],
      }).success,
    ).toBe(true);
  });
});
