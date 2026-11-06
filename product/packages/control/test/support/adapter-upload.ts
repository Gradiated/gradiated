export const adapterFiles = (
  baseModel: string,
  layerCount = 1,
  expertIndices?: readonly number[] | number,
  rank = 2,
) => {
  const config = Buffer.from(
    JSON.stringify({
      peft_type: "LORA",
      task_type: "CAUSAL_LM",
      base_model_name_or_path: baseModel,
      r: rank,
      lora_alpha: 4,
      target_modules: [expertIndices ? "down_proj" : "q_proj"],
      bias: "none",
    }),
  );
  const fusedCount =
    typeof expertIndices === "number" ? expertIndices : undefined;
  const indices =
    typeof expertIndices === "number" ? [null] : (expertIndices ?? [null]);
  const tensorBytes = 4 * rank * 4 * (fusedCount ?? 1);
  const paths = Array.from({ length: layerCount }, (_, layer) =>
    indices.map((expert, ordinal) => ({
      path: `base_model.model.layers.${layer}.${fusedCount ? "mlp.experts.down_proj" : expert === null ? "self_attn.q_proj" : `mlp.experts.${expert}.down_proj`}`,
      offset: (layer * indices.length + ordinal) * tensorBytes * 2,
    })),
  ).flat();
  const tensors = Object.fromEntries(
    paths
      .map(({ path, offset }) => [
        [
          `${path}.lora_A.weight`,
          {
            dtype: "F32",
            shape: fusedCount ? [fusedCount, rank, 4] : [rank, 4],
            data_offsets: [offset, offset + tensorBytes],
          },
        ],
        [
          `${path}.lora_B.weight`,
          {
            dtype: "F32",
            shape: fusedCount ? [fusedCount, 4, rank] : [4, rank],
            data_offsets: [offset + tensorBytes, offset + tensorBytes * 2],
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
    weights: Buffer.concat([
      length,
      header,
      Buffer.alloc(tensorBytes * 2 * paths.length),
    ]),
  };
};
