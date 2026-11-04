import { describe, expect, it } from "vitest";
import { adapterProjectionShapes } from "@gradiated/contracts/adapter-shapes";
import { validateAdapterFiles } from "../src/training/adapter-upload.js";
import { adapterFiles } from "./support/adapter-upload.js";

const qwen = {
  model_type: "qwen3",
  hidden_size: 4,
  num_hidden_layers: 1,
  num_attention_heads: 2,
  num_key_value_heads: 1,
  head_dim: 2,
  intermediate_size: 8,
};
const check = (
  shapes: NonNullable<ReturnType<typeof adapterProjectionShapes>>,
  patch = {},
) => {
  const files = adapterFiles("test/base");
  return validateAdapterFiles(
    Buffer.from(
      JSON.stringify({ ...JSON.parse(files.config.toString()), ...patch }),
    ),
    {
      sizeBytes: files.weights.length,
      read: async (offset, length) =>
        files.weights.subarray(offset, offset + length),
    },
    "test/base",
    { layerCount: 1, expertCount: 0, projectionShapes: shapes },
  );
};
describe("serving adapter dimensions", () => {
  it("derives grouped-query attention and dense MLP dimensions", () => {
    expect(adapterProjectionShapes(qwen)).toMatchObject({
      "0/self_attn.q_proj": [4, 4],
      "0/self_attn.k_proj": [2, 4],
      "0/mlp.down_proj": [4, 8],
    });
  });
  it("derives hybrid GLM attention from each layer's actual architecture", () => {
    expect(
      adapterProjectionShapes({
        model_type: "glm5_next_text",
        hidden_size: 4,
        num_hidden_layers: 2,
        num_attention_heads: 2,
        layer_types: ["linear_attention", "deepseek_sparse_attention"],
        linear_attn_config: { num_heads: 3, head_dim: 2 },
        q_lora_rank: 2,
        kv_lora_rank: 1,
        qk_rope_head_dim: 0,
        qk_nope_head_dim: 2,
        v_head_dim: 2,
      }),
    ).toEqual({
      "0/self_attn.q_proj": [6, 4],
      "0/self_attn.k_proj": [6, 4],
      "0/self_attn.v_proj": [6, 4],
      "0/self_attn.o_proj": [4, 6],
      "1/self_attn.q_a_proj": [2, 4],
      "1/self_attn.q_b_proj": [4, 2],
      "1/self_attn.kv_a_proj_with_mqa": [1, 4],
      "1/self_attn.kv_b_proj": [8, 1],
      "1/self_attn.o_proj": [4, 4],
    });
  });
  it("derives DeepSeek V4.1 low-rank attention and shared experts", () => {
    const shapes = adapterProjectionShapes({
      model_type: "deepseek_v41_text",
      hidden_size: 5120,
      num_hidden_layers: 40,
      num_attention_heads: 64,
      num_key_value_heads: 1,
      head_dim: 512,
      q_lora_rank: 1280,
      o_lora_rank: 1024,
      o_groups: 8,
      moe_intermediate_size: 2304,
    });

    // Matches the tensors in deepseek-ai/DeepSeek-V4.1-Flash at dba1be0.
    expect(shapes).toMatchObject({
      "39/attn.wq_a": [1280, 5120],
      "39/attn.wq_b": [32768, 1280],
      "39/attn.wkv": [512, 5120],
      "39/attn.wo_a": [8192, 4096],
      "39/attn.wo_b": [5120, 8192],
      "39/ffn.shared_experts.w1": [2304, 5120],
      "39/ffn.shared_experts.w2": [5120, 2304],
      "39/ffn.shared_experts.w3": [2304, 5120],
    });
    expect(Object.keys(shapes ?? {})).toHaveLength(320);
  });

  it("does not assume unknown architectures are supported", () => {
    expect(
      adapterProjectionShapes({ ...qwen, model_type: "unknown" }),
    ).toBeUndefined();
  });
  it("accepts matching shapes even without checkpoint metadata", async () => {
    expect((await check(adapterProjectionShapes(qwen)!)).r).toBe(2);
  });
  it.each([
    [8, 4],
    [4, 8],
  ])(
    "rejects a rank-correct tensor whose output/input dimensions are %j",
    async (output, input) => {
      await expect(
        check({ "0/self_attn.q_proj": [output!, input!] }),
      ).rejects.toThrow("dimensions");
    },
  );
  it("rejects unsupported module paths instead of matching only a leaf name", async () => {
    await expect(check({ "0/mlp.q_proj": [4, 4] })).rejects.toThrow(
      "not supported",
    );
  });
  it("rejects configured target modules that have no tensors", async () => {
    await expect(
      check(adapterProjectionShapes(qwen)!, {
        target_modules: ["q_proj", "k_proj"],
      }),
    ).rejects.toThrow("no tensors");
  });
  it.each([
    "use_rslora",
    "use_qalora",
    "use_dora",
    "fan_in_fan_out",
    "lora_bias",
  ])("rejects unsupported feature %s", async (feature) => {
    await expect(
      check(adapterProjectionShapes(qwen)!, { [feature]: true }),
    ).rejects.toThrow();
  });
});
