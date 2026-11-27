import { readFileSync } from "node:fs";
import { expect, it } from "vitest";
import { MAX_UPLOADED_ADAPTER_RANK } from "@gradiated/contracts";
import { adapterProjectionShapes } from "@gradiated/contracts/adapter-shapes";

// SGLang preallocates bf16 A and B buffers for every GPU slot at the maximum
// rank, sharded across tensor-parallel ranks; CPU slots hold the same tensors.
const GPU_BUDGET_BYTES = 2 * 1024 ** 3;
const CPU_BUDGET_FRACTION = 0.1;

type Runtime = {
  model_id: string;
  adapters?: boolean;
  memory: string;
  release: { lora_enabled?: boolean };
  environment: Record<string, string>;
};

const runtimes = Object.values(
  JSON.parse(
    readFileSync(
      new URL("../../../inference/gpu/runtimes.json", import.meta.url),
      "utf8",
    ),
  ) as Record<string, Runtime>,
).filter((runtime) => runtime.release.lora_enabled);
// Trimmed from each pool model's pinned Hugging Face config.json.
const configs = JSON.parse(
  readFileSync(
    new URL("fixtures/lora-pool-configs.json", import.meta.url),
    "utf8",
  ),
) as Record<string, unknown>;

const gibibytes = (value: string) => {
  const match = /^(\d+)Gi$/.exec(value);
  if (!match) throw new Error(`Unexpected memory size ${value}`);

  return Number(match[1]) * 1024 ** 3;
};

const adapterBytes = (config: unknown, rank: number) => {
  const shapes = adapterProjectionShapes(config);
  if (!shapes) throw new Error("No adapter layout for this architecture.");

  let elements = 0;
  for (const [output, input] of Object.values(shapes))
    elements += rank * (output + input);

  return elements * 2;
};

it("finds the LoRA pools it checks", () => {
  expect(runtimes.length).toBeGreaterThan(0);
});

it.each(runtimes.map((runtime) => [runtime.model_id, runtime] as const))(
  "%s serves the upload rank cap within its adapter memory",
  (modelId, runtime) => {
    const rank = Number(runtime.environment.LORA_MAX_RANK);
    const gpuSlots = Number(runtime.environment.LORA_GPU_SLOTS);
    const cpuSlots = Number(runtime.environment.LORA_CPU_SLOTS);
    const parallel = Number(runtime.environment.TENSOR_PARALLEL_SIZE ?? 1);
    const config = configs[runtime.environment.MODEL_ID ?? modelId];
    expect(config, `pinned config for ${modelId}`).toBeDefined();

    expect(rank).toBeGreaterThanOrEqual(MAX_UPLOADED_ADAPTER_RANK);
    const perAdapter = adapterBytes(config, rank);
    expect(perAdapter * (gpuSlots / parallel)).toBeLessThanOrEqual(
      GPU_BUDGET_BYTES,
    );
    expect(perAdapter * cpuSlots).toBeLessThanOrEqual(
      gibibytes(runtime.memory) * CPU_BUDGET_FRACTION,
    );
  },
);
