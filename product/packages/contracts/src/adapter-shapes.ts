import { z } from "zod";

const DimensionSchema = z.number().int().positive().max(1_000_000);
const CommonSchema = z
  .object({
    model_type: z.string(),
    hidden_size: DimensionSchema,
    num_hidden_layers: DimensionSchema.max(4096),
    num_attention_heads: DimensionSchema,
  })
  .passthrough();
export type ProjectionShapes = Record<string, readonly [number, number]>;

export const adapterProjectionShapes = (
  value: unknown,
): ProjectionShapes | undefined => {
  const parsed = CommonSchema.safeParse(value);
  if (!parsed.success) return undefined;
  const config = parsed.data;
  const hidden = config.hidden_size;
  const heads = config.num_attention_heads;
  const shapes: ProjectionShapes = {};
  const add = (layer: number, name: string, output: number, input: number) => {
    shapes[`${layer}/${name}`] = [
      DimensionSchema.parse(output),
      DimensionSchema.parse(input),
    ];
  };
  if (config.model_type === "qwen3" || config.model_type === "qwen2") {
    const head = DimensionSchema.parse(config.head_dim ?? hidden / heads);
    const kvHeads = DimensionSchema.parse(config.num_key_value_heads);
    const intermediate = DimensionSchema.parse(config.intermediate_size);
    for (let layer = 0; layer < config.num_hidden_layers; layer++) {
      add(layer, "self_attn.q_proj", heads * head, hidden);
      add(layer, "self_attn.k_proj", kvHeads * head, hidden);
      add(layer, "self_attn.v_proj", kvHeads * head, hidden);
      add(layer, "self_attn.o_proj", hidden, heads * head);
      add(layer, "mlp.gate_proj", intermediate, hidden);
      add(layer, "mlp.up_proj", intermediate, hidden);
      add(layer, "mlp.down_proj", hidden, intermediate);
    }
    return shapes;
  }
  if (config.model_type === "glm5_next_text") {
    const types = z
      .array(z.enum(["linear_attention", "deepseek_sparse_attention"]))
      .length(config.num_hidden_layers)
      .parse(config.layer_types);
    const linear = z
      .object({ num_heads: DimensionSchema, head_dim: DimensionSchema })
      .parse(config.linear_attn_config);
    const qRank = DimensionSchema.parse(config.q_lora_rank);
    const kvRank = DimensionSchema.parse(config.kv_lora_rank);
    const rope = z.number().int().nonnegative().parse(config.qk_rope_head_dim);
    const nope = DimensionSchema.parse(config.qk_nope_head_dim);
    const vHead = DimensionSchema.parse(config.v_head_dim);
    for (const [layer, kind] of types.entries()) {
      if (kind === "linear_attention") {
        for (const module of ["q_proj", "k_proj", "v_proj"])
          add(
            layer,
            `self_attn.${module}`,
            linear.num_heads * linear.head_dim,
            hidden,
          );
        add(
          layer,
          "self_attn.o_proj",
          hidden,
          linear.num_heads * linear.head_dim,
        );
      } else {
        add(layer, "self_attn.q_a_proj", qRank, hidden);
        add(layer, "self_attn.q_b_proj", heads * (nope + rope), qRank);
        add(layer, "self_attn.kv_a_proj_with_mqa", kvRank + rope, hidden);
        add(layer, "self_attn.kv_b_proj", heads * (nope + vHead), kvRank);
        add(layer, "self_attn.o_proj", hidden, heads * vHead);
      }
    }
    return shapes;
  }
  if (config.model_type === "deepseek_v41_text") {
    const head = DimensionSchema.parse(config.head_dim);
    const kvHeads = DimensionSchema.parse(config.num_key_value_heads);
    const qRank = DimensionSchema.parse(config.q_lora_rank);
    const oRank = DimensionSchema.parse(config.o_lora_rank);
    const oGroups = DimensionSchema.parse(config.o_groups);
    const expert = DimensionSchema.parse(config.moe_intermediate_size);
    for (let layer = 0; layer < config.num_hidden_layers; layer++) {
      add(layer, "attn.wq_a", qRank, hidden);
      add(layer, "attn.wq_b", heads * head, qRank);
      add(layer, "attn.wkv", kvHeads * head, hidden);
      add(layer, "attn.wo_a", oGroups * oRank, (heads * head) / oGroups);
      add(layer, "attn.wo_b", hidden, oGroups * oRank);
      add(layer, "ffn.shared_experts.w1", expert, hidden);
      add(layer, "ffn.shared_experts.w2", hidden, expert);
      add(layer, "ffn.shared_experts.w3", expert, hidden);
    }
    return shapes;
  }
  return undefined;
};
