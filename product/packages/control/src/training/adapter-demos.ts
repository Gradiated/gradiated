import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  CreateBucketCommand,
  PutBucketVersioningCommand,
  S3Client,
} from "@aws-sdk/client-s3";
import { and, eq } from "drizzle-orm";
import { v7 as uuidv7 } from "uuid";
import { adapterProjectionShapes } from "@gradiated/contracts/adapter-shapes";
import type { ControlDatabase } from "../db/client.js";
import { tasks, taskVersions, workspaces } from "../db/schema/index.js";
import { ObjectStorage } from "../storage/object-storage.js";
import { adapterArchive } from "./adapter-upload.js";
import { TaskRecordSchema, VersionInsertSchema } from "./records.js";

// Local development only. The LoRA weights are seeded noise with layer profiles
// and hot bands, shaped like real adapters on these bases; they are never served.

type Shapes = Record<string, readonly [number, number]>;
type Demo = {
  task: string;
  baseModelId: string;
  repository: string;
  rank: number;
  shapes: () => Shapes;
  peak: number;
};

const range = (start: number, end: number) =>
  Array.from({ length: end - start }, (_, index) => start + index);

// Trimmed from each model's pinned config.json.
const deepseek = {
  model_type: "deepseek_v41_text",
  vocab_size: 129_280,
  hidden_size: 5120,
  num_hidden_layers: 40,
  num_attention_heads: 64,
  num_key_value_heads: 1,
  head_dim: 512,
  q_lora_rank: 1280,
  o_lora_rank: 1024,
  o_groups: 8,
  moe_intermediate_size: 2304,
};
const glmLayerTypes = range(0, 45).map((layer) =>
  layer % 4 === 3 ? "deepseek_sparse_attention" : "linear_attention",
);
const glm = {
  model_type: "glm5_next_text",
  hidden_size: 4096,
  num_hidden_layers: 45,
  num_attention_heads: 64,
  layer_types: glmLayerTypes,
  linear_attn_config: { num_heads: 64, head_dim: 128 },
  q_lora_rank: 1536,
  kv_lora_rank: 512,
  qk_rope_head_dim: 0,
  qk_nope_head_dim: 256,
  v_head_dim: 256,
};
// Kimi K3.1 Pro has no adapter shapes in the catalog yet; these follow its
// config's MLA dimensions (hidden 7168, 96 heads, q/kv LoRA ranks 1536/512).
const kimiAttention = () => {
  const shapes: Shapes = {};
  for (const layer of range(0, 93)) {
    shapes[`${layer}/self_attn.q_a_proj`] = [1536, 7168];
    shapes[`${layer}/self_attn.q_b_proj`] = [96 * 192, 1536];
    shapes[`${layer}/self_attn.kv_a_proj_with_mqa`] = [576, 7168];
    shapes[`${layer}/self_attn.kv_b_proj`] = [96 * 256, 512];
    shapes[`${layer}/self_attn.o_proj`] = [7168, 96 * 128];
  }
  return shapes;
};

export const ADAPTER_DEMOS: readonly Demo[] = [
  {
    task: "flash-head",
    baseModelId: "deepseek/deepseek-v4.1-flash-1017",
    repository: "deepseek-ai/DeepSeek-V4.1-Flash-1017",
    rank: 4,
    shapes: () => ({ lm_head: adapterProjectionShapes(deepseek)!.lm_head! }),
    peak: 1,
  },
  {
    task: "flash-attention",
    baseModelId: "deepseek/deepseek-v4.1-flash-1017",
    repository: "deepseek-ai/DeepSeek-V4.1-Flash-1017",
    rank: 4,
    shapes: () =>
      Object.fromEntries(
        Object.entries(adapterProjectionShapes(deepseek)!).filter(([key]) =>
          /\/(attn\.(wq_b|wkv|wo_b)|ffn\.shared_experts\.w2)$/.test(key),
        ),
      ),
    peak: 0.7,
  },
  {
    task: "glm-triage",
    baseModelId: "z-ai/glm-5.3-flash",
    repository: "zai-org/GLM-5.3-Flash-BF16",
    rank: 4,
    shapes: () => adapterProjectionShapes(glm)!,
    peak: 0.45,
  },
  {
    task: "kimi-research",
    baseModelId: "moonshotai/kimi-k3.1-pro",
    repository: "moonshotai/Kimi-K3.1-Pro",
    rank: 2,
    shapes: kimiAttention,
    peak: 0.8,
  },
];

const generator = (seed: number) => {
  let state = seed >>> 0 || 1;
  const uniform = () => {
    state = (state + 0x6d2b79f5) | 0;
    let t = Math.imul(state ^ (state >>> 15), 1 | state);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4_294_967_296;
  };
  const gaussian = () =>
    Math.sqrt(-2 * Math.log(1 - uniform())) * Math.cos(2 * Math.PI * uniform());
  return { uniform, gaussian };
};

const bands = (size: number, random: ReturnType<typeof generator>) => {
  const scale = new Float32Array(size).fill(1);
  const width = Math.max(1, Math.floor(size / 24));
  for (let band = 0; band < 3; band++) {
    const start = Math.floor(random.uniform() * (size - width));
    const gain = 2 + random.uniform() * 4;
    for (let index = start; index < start + width; index++) scale[index] = gain;
  }
  return scale;
};

const bf16 = (values: Float32Array) =>
  new Uint8Array(
    Uint16Array.from(new Uint32Array(values.buffer), (bits) => bits >>> 16)
      .buffer,
  );

const safetensors = (demo: Demo, seed: number) => {
  const random = generator(seed);
  const shapes = Object.entries(demo.shapes());
  const layers = Math.max(
    1,
    ...shapes.map(([key]) => Number(key.split("/")[0]) + 1 || 1),
  );
  const factors = new Map<string, number>();
  const header: Record<string, unknown> = {};
  const parts: Uint8Array[] = [];
  let offset = 0;
  for (const [key, [outputs, inputs]] of shapes) {
    const [layer, ...rest] = key.split("/");
    const head = !rest.length;
    const module = head ? "lm_head" : rest.join("/");
    const name = head
      ? "base_model.model.lm_head"
      : `base_model.model.model.layers.${layer}.${module}`;
    const position = head ? 1 : Number(layer) / Math.max(layers - 1, 1);
    const profile =
      0.25 +
      Math.exp(-(((position - demo.peak) / 0.15) ** 2)) +
      0.4 * Math.exp(-(((position - 0.1) / 0.07) ** 2));
    if (!factors.has(module)) factors.set(module, 0.4 + random.uniform() * 1.3);
    const amplitude = 0.01 * profile * factors.get(module)!;
    const columns = bands(inputs, random);
    const rows = bands(outputs, random);
    const a = new Float32Array(demo.rank * inputs);
    for (let rank = 0; rank < demo.rank; rank++)
      for (let input = 0; input < inputs; input++)
        a[rank * inputs + input] =
          (random.gaussian() * columns[input]!) / Math.sqrt(inputs);
    const b = new Float32Array(outputs * demo.rank);
    for (let output = 0; output < outputs; output++)
      for (let rank = 0; rank < demo.rank; rank++)
        b[output * demo.rank + rank] =
          random.gaussian() * rows[output]! * amplitude * 0.55 ** rank;
    for (const [side, values, shape] of [
      ["A", a, [demo.rank, inputs]],
      ["B", b, [outputs, demo.rank]],
    ] as const) {
      const bytes = bf16(values);
      header[`${name}.lora_${side}.weight`] = {
        dtype: "BF16",
        shape,
        data_offsets: [offset, offset + bytes.length],
      };
      offset += bytes.length;
      parts.push(bytes);
    }
  }
  const json = Buffer.from(JSON.stringify(header));
  const size = Buffer.alloc(8);
  size.writeBigUInt64LE(BigInt(json.length));
  return Buffer.concat([size, json, ...parts]);
};

const ensureVersionedBucket = async (bucket: string) => {
  const client = new S3Client({});
  try {
    await client.send(new CreateBucketCommand({ Bucket: bucket }));
  } catch (error) {
    const name = (error as { name?: string }).name;
    if (name !== "BucketAlreadyOwnedByYou" && name !== "BucketAlreadyExists")
      throw error;
  }
  await client.send(
    new PutBucketVersioningCommand({
      Bucket: bucket,
      VersioningConfiguration: { Status: "Enabled" },
    }),
  );
  client.destroy();
};

export const seedAdapterDemos = async ({
  database,
  bucket,
  organizationId,
}: {
  database: ControlDatabase;
  bucket: string;
  organizationId: string;
}) => {
  const endpoint = process.env.AWS_ENDPOINT_URL_S3 ?? "";
  if (!/^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?\/?$/.test(endpoint))
    throw new Error(
      "Adapter demos seed only into local object storage (AWS_ENDPOINT_URL_S3 on loopback).",
    );

  const [workspace] = await database
    .select()
    .from(workspaces)
    .where(
      and(
        eq(workspaces.organizationId, organizationId),
        eq(workspaces.isDefault, true),
      ),
    );
  if (!workspace) throw new Error("The organization has no default workspace.");

  await ensureVersionedBucket(bucket);
  const storage = new ObjectStorage(bucket);
  const directory = await mkdtemp(join(tmpdir(), "gradiated-adapter-demo-"));
  const seeded: string[] = [];
  try {
    for (const [index, demo] of ADAPTER_DEMOS.entries()) {
      const [existing] = await database
        .select({ id: tasks.id })
        .from(tasks)
        .where(
          and(eq(tasks.workspaceId, workspace.id), eq(tasks.name, demo.task)),
        );
      if (existing) continue;

      const versionId = uuidv7();
      const config = Buffer.from(
        JSON.stringify({
          peft_type: "LORA",
          task_type: "CAUSAL_LM",
          base_model_name_or_path: demo.repository,
          r: demo.rank,
          lora_alpha: demo.rank * 2,
          target_modules: [
            ...new Set(
              Object.keys(demo.shapes()).map((key) =>
                key.split("/").at(-1)!.split(".").at(-1)!,
              ),
            ),
          ],
          bias: "none",
        }),
      );
      const weightsPath = join(directory, `${demo.task}.safetensors`);
      const weights = safetensors(demo, index + 1);
      await writeFile(weightsPath, weights);
      const archivePath = join(directory, `${demo.task}.tar.gz`);
      const archive = await adapterArchive(
        config,
        weightsPath,
        weights.length,
        archivePath,
      );
      const key = `runs/${versionId}/output/${archive.sha256}/adapter.tar.gz`;
      await storage.putFile(key, archivePath, archive);
      await database.transaction(async (tx) => {
        const taskId = uuidv7();
        await tx.insert(tasks).values(
          TaskRecordSchema.omit({ createdAt: true, updatedAt: true }).parse({
            id: taskId,
            organizationId: null,
            workspaceId: workspace.id,
            name: demo.task,
            baseModelId: demo.baseModelId,
            comparisonModelId: null,
            judgeModelId: workspace.defaultJudgeModel,
            productionVersionId: null,
            trainingSchedule: null,
          }),
        );
        await tx.insert(taskVersions).values(
          VersionInsertSchema.parse({
            id: versionId,
            workspaceId: workspace.id,
            taskId,
            trainingRunId: null,
            name: "v1",
            baseModelId: demo.baseModelId,
            adapter: {
              format: "peft_lora",
              artifact_uri: storage.uri(key),
              sha256: archive.sha256,
              size_bytes: archive.sizeBytes,
              rank: demo.rank,
            },
            status: "unavailable",
          }),
        );
      });
      seeded.push(
        `${demo.task}/v1 (${(weights.length / 2 ** 20).toFixed(0)} MiB)`,
      );
    }
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
  return seeded;
};
