import { createGzip } from "node:zlib";
import { Readable } from "node:stream";
import { z } from "zod";

const ConfigSchema = z
  .object({
    peft_type: z.literal("LORA"),
    task_type: z.literal("CAUSAL_LM"),
    base_model_name_or_path: z.string().min(1),
    r: z.number().int().min(1).max(256),
    lora_alpha: z.number().positive(),
    target_modules: z.array(z.string().min(1)).min(1),
    use_dora: z.literal(false).optional(),
    modules_to_save: z.null().optional(),
    bias: z.literal("none"),
    rank_pattern: z.record(z.string(), z.never()).optional(),
    alpha_pattern: z.record(z.string(), z.never()).optional(),
    target_parameters: z.null().optional(),
    auto_mapping: z.null().optional(),
  })
  .passthrough();

export const validateAdapterFiles = (
  configBytes: Uint8Array,
  weights: Uint8Array,
  baseModel: string,
) => {
  const config = ConfigSchema.parse(
    JSON.parse(Buffer.from(configBytes).toString("utf8")),
  );
  if (config.base_model_name_or_path !== baseModel)
    throw new Error(
      "The adapter config does not match the selected base model.",
    );

  const bytes = Buffer.from(
    weights.buffer,
    weights.byteOffset,
    weights.byteLength,
  );
  if (bytes.length < 10)
    throw new Error("The safetensors file is empty or invalid.");

  const headerSize = Number(bytes.readBigUInt64LE());
  if (
    !Number.isSafeInteger(headerSize) ||
    headerSize < 2 ||
    headerSize > 1024 * 1024 ||
    headerSize + 8 >= bytes.length
  )
    throw new Error("Invalid safetensors header.");

  const tensors = z
    .record(z.string(), z.unknown())
    .parse(JSON.parse(bytes.subarray(8, 8 + headerSize).toString("utf8")));
  const ranges: [number, number][] = [];
  const names = Object.keys(tensors).filter((name) => name !== "__metadata__");
  if (!names.length) throw new Error("The adapter contains no tensors.");

  for (const name of names) {
    if (!/\.lora_[AB](?:\.default)?\.weight$/.test(name))
      throw new Error("Only LoRA A/B weight tensors are supported.");

    const tensor = z
      .object({
        dtype: z.enum(["F16", "BF16", "F32"]),
        shape: z.tuple([
          z.number().int().positive(),
          z.number().int().positive(),
        ]),
        data_offsets: z.tuple([
          z.number().int().nonnegative(),
          z.number().int().positive(),
        ]),
      })
      .parse(tensors[name]);
    const [start, end] = tensor.data_offsets;
    const width = tensor.dtype === "F32" ? 4 : 2;
    const isA = /\.lora_A(?:\.default)?\.weight$/.test(name);
    const pair = name.replace(
      isA ? ".lora_A" : ".lora_B",
      isA ? ".lora_B" : ".lora_A",
    );
    if (
      tensor.shape[isA ? 0 : 1] !== config.r ||
      !(pair in tensors) ||
      end - start !== tensor.shape[0] * tensor.shape[1] * width
    )
      throw new Error(
        "Adapter tensor ranks, pairs or sizes do not match the config.",
      );

    const moduleName = name
      .replace(/\.lora_[AB](?:\.default)?\.weight$/, "")
      .split(".")
      .at(-1);
    if (!moduleName || !config.target_modules.includes(moduleName))
      throw new Error("Tensor target modules do not match the config.");

    const dataStart = 8 + headerSize + start;
    if (end > bytes.length - headerSize - 8)
      throw new Error("Tensor exceeds the file bounds.");

    for (let offset = 0; offset < end - start; offset += width) {
      const value =
        width === 4
          ? bytes.readUInt32LE(dataStart + offset)
          : bytes.readUInt16LE(dataStart + offset);
      const mask =
        tensor.dtype === "F32"
          ? 0x7f800000
          : tensor.dtype === "F16"
            ? 0x7c00
            : 0x7f80;
      if ((value & mask) === mask)
        throw new Error("Adapter contains non-finite tensor values.");
    }
    ranges.push([start, end]);
  }
  ranges.sort((a, b) => a[0] - b[0]);
  let offset = 0;
  for (const [start, end] of ranges) {
    if (start !== offset || end <= start)
      throw new Error("Invalid tensor offsets.");

    offset = end;
  }
  if (offset !== bytes.length - headerSize - 8)
    throw new Error("Invalid tensor data length.");

  return config;
};

export const adapterArchive = async (
  config: Uint8Array,
  weights: Uint8Array,
) => {
  const parts: Uint8Array[] = [];
  for (const [name, data] of [
    ["adapter_config.json", config],
    ["adapter_model.safetensors", weights],
  ] as const) {
    const header = Buffer.alloc(512);
    header.write(name);
    header.write("0000644\0", 100);
    header.write("0000000\0", 108);
    header.write("0000000\0", 116);
    header.write(data.length.toString(8).padStart(11, "0") + "\0", 124);
    header.write("00000000000\0", 136);
    header.fill(32, 148, 156);
    header.write("0", 156);
    header.write("ustar\0", 257);
    header.write("00", 263);
    const checksum = header.reduce((sum, byte) => sum + byte, 0);
    header.write(checksum.toString(8).padStart(6, "0") + "\0 ", 148);
    parts.push(header, data, Buffer.alloc((512 - (data.length % 512)) % 512));
  }
  parts.push(Buffer.alloc(1024));
  const compressed = Readable.from(parts).pipe(createGzip({ level: 1 }));
  const chunks: Buffer[] = [];
  for await (const chunk of compressed) chunks.push(chunk as Buffer);

  return Buffer.concat(chunks);
};
