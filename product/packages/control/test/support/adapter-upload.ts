export const adapterFiles = (
  baseModel: string,
  layerCount = 1,
  expertIndices?: readonly number[],
) => {
  const config = Buffer.from(
    JSON.stringify({
      peft_type: "LORA",
      task_type: "CAUSAL_LM",
      base_model_name_or_path: baseModel,
      r: 2,
      lora_alpha: 4,
      target_modules: [expertIndices ? "down_proj" : "q_proj"],
      bias: "none",
    }),
  );
  const indices = expertIndices ?? [null];
  const paths = Array.from({ length: layerCount }, (_, layer) =>
    indices.map((expert, ordinal) => ({
      path: `base_model.model.layers.${layer}.${expert === null ? "self_attn.q_proj" : `mlp.experts.${expert}.down_proj`}`,
      offset: (layer * indices.length + ordinal) * 64,
    })),
  ).flat();
  const tensors = Object.fromEntries(
    paths
      .map(({ path, offset }) => [
        [
          `${path}.lora_A.weight`,
          { dtype: "F32", shape: [2, 4], data_offsets: [offset, offset + 32] },
        ],
        [
          `${path}.lora_B.weight`,
          {
            dtype: "F32",
            shape: [4, 2],
            data_offsets: [offset + 32, offset + 64],
          },
        ],
      ])
      .flat(),
  );
  const header = Buffer.from(JSON.stringify(tensors));
  const length = Buffer.alloc(8);
  length.writeBigUInt64LE(BigInt(header.length));
  return {
    config,
    weights: Buffer.concat([length, header, Buffer.alloc(64 * paths.length)]),
  };
};
