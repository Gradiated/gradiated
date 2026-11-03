import { createGzip } from "node:zlib";
import { Readable, Transform } from "node:stream";
import { pipeline } from "node:stream/promises";
import { createReadStream, createWriteStream } from "node:fs";
import { createHash } from "node:crypto";
import type { FileHandle } from "node:fs/promises";
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

export const adapterFileReader = (file: FileHandle, sizeBytes: number) => ({
  sizeBytes,
  read: async (offset: number, length: number): Promise<Buffer> => {
    const bytes = Buffer.alloc(length);
    let received = 0;
    while (received < length) {
      const result = await file.read(
        bytes,
        received,
        length - received,
        offset + received,
      );
      if (!result.bytesRead) throw new Error("Adapter file was truncated.");

      received += result.bytesRead;
    }
    return bytes;
  },
});

export const validateAdapterFiles = async (
  configBytes: Uint8Array,
  weights: ReturnType<typeof adapterFileReader>,
  baseModel: string,
) => {
  const config = ConfigSchema.parse(
    JSON.parse(Buffer.from(configBytes).toString("utf8")),
  );
  if (config.base_model_name_or_path !== baseModel)
    throw new Error(
      "The adapter config does not match the selected base model.",
    );

  if (weights.sizeBytes < 10)
    throw new Error("The safetensors file is empty or invalid.");

  const bytes = await weights.read(0, 8);
  const headerSize = Number(bytes.readBigUInt64LE());
  if (
    !Number.isSafeInteger(headerSize) ||
    headerSize < 2 ||
    headerSize > 1024 * 1024 ||
    headerSize + 8 >= weights.sizeBytes
  )
    throw new Error("Invalid safetensors header.");

  const tensors = z
    .record(z.string(), z.unknown())
    .parse(JSON.parse((await weights.read(8, headerSize)).toString("utf8")));
  const ranges: [number, number, number, number][] = [];
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

    if (end > weights.sizeBytes - headerSize - 8)
      throw new Error("Tensor exceeds the file bounds.");

    const mask =
      tensor.dtype === "F32"
        ? 0x7f800000
        : tensor.dtype === "F16"
          ? 0x7c00
          : 0x7f80;
    ranges.push([start, end, width, mask]);
  }
  ranges.sort((a, b) => a[0] - b[0]);
  let offset = 0;
  for (const [start, end] of ranges) {
    if (start !== offset || end <= start)
      throw new Error("Invalid tensor offsets.");

    offset = end;
  }
  if (offset !== weights.sizeBytes - headerSize - 8)
    throw new Error("Invalid tensor data length.");

  for (const [start, end, width, mask] of ranges) {
    for (let offset = 0; offset < end - start; offset += 64 * 1024) {
      const chunk = await weights.read(
        8 + headerSize + start + offset,
        Math.min(64 * 1024, end - start - offset),
      );
      for (let index = 0; index < chunk.length; index += width) {
        const value =
          width === 4 ? chunk.readUInt32LE(index) : chunk.readUInt16LE(index);
        if ((value & mask) === mask)
          throw new Error("Adapter contains non-finite tensor values.");
      }
    }
  }

  return config;
};

export const adapterArchive = async (
  config: Uint8Array,
  weightsPath: string,
  weightsSize: number,
  destination: string,
) => {
  const parts = async function* () {
    for (const [name, size] of [
      ["adapter_config.json", config.length],
      ["adapter_model.safetensors", weightsSize],
    ] as const) {
      const header = Buffer.alloc(512);
      header.write(name);
      header.write("0000644\0", 100);
      header.write("0000000\0", 108);
      header.write("0000000\0", 116);
      header.write(size.toString(8).padStart(11, "0") + "\0", 124);
      header.write("00000000000\0", 136);
      header.fill(32, 148, 156);
      header.write("0", 156);
      header.write("ustar\0", 257);
      header.write("00", 263);
      const checksum = header.reduce((sum, byte) => sum + byte, 0);
      header.write(checksum.toString(8).padStart(6, "0") + "\0 ", 148);
      yield header;
      if (name === "adapter_config.json") yield config;
      else yield* createReadStream(weightsPath, { highWaterMark: 64 * 1024 });
      yield Buffer.alloc((512 - (size % 512)) % 512);
    }
    yield Buffer.alloc(1024);
  };
  const hash = createHash("sha256");
  let sizeBytes = 0;
  const digest = new Transform({
    transform(chunk: Buffer, _encoding, callback) {
      hash.update(chunk);
      sizeBytes += chunk.length;
      callback(null, chunk);
    },
  });
  await pipeline(
    Readable.from(parts()),
    createGzip({ level: 1 }),
    digest,
    createWriteStream(destination, { flags: "wx" }),
    { signal: AbortSignal.timeout(120_000) },
  );

  return { sha256: hash.digest("hex"), sizeBytes };
};
