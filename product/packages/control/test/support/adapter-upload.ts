export const adapterFiles = (baseModel: string) => {
  const config = Buffer.from(
    JSON.stringify({
      peft_type: "LORA",
      task_type: "CAUSAL_LM",
      base_model_name_or_path: baseModel,
      r: 2,
      lora_alpha: 4,
      target_modules: ["q_proj"],
      bias: "none",
    }),
  );
  const header = Buffer.from(
    JSON.stringify({
      "base_model.model.layers.0.self_attn.q_proj.lora_A.weight": {
        dtype: "F32",
        shape: [2, 4],
        data_offsets: [0, 32],
      },
      "base_model.model.layers.0.self_attn.q_proj.lora_B.weight": {
        dtype: "F32",
        shape: [4, 2],
        data_offsets: [32, 64],
      },
    }),
  );
  const length = Buffer.alloc(8);
  length.writeBigUInt64LE(BigInt(header.length));
  return { config, weights: Buffer.concat([length, header, Buffer.alloc(64)]) };
};
