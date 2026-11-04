import { createGzip } from "node:zlib";
import { Readable, Transform } from "node:stream";
import { pipeline } from "node:stream/promises";
import { createReadStream, createWriteStream } from "node:fs";
import { createHash } from "node:crypto";
import { TextDecoder } from "node:util";
import type { FileHandle } from "node:fs/promises";
import { z } from "zod";
import { MAX_UPLOADED_ADAPTER_RANK } from "@gradiated/contracts";
import type { BaseModelConfiguration } from "./base-model-configuration.js";

const ConfigSchema = z
  .object({
    peft_type: z.literal("LORA"),
    task_type: z.literal("CAUSAL_LM"),
    base_model_name_or_path: z.string().min(1),
    revision: z.string().max(300).nullish(),
    r: z.number().int().min(1).max(MAX_UPLOADED_ADAPTER_RANK),
    lora_alpha: z.number().positive(),
    target_modules: z.array(z.string().min(1)).min(1),
    use_dora: z.literal(false).optional(),
    use_rslora: z.literal(false).optional(),
    use_qalora: z.literal(false).optional(),
    lora_bias: z.literal(false).optional(),
    fan_in_fan_out: z.literal(false).optional(),
    layer_replication: z.null().optional(),
    layers_to_transform: z.null().optional(),
    layers_pattern: z.null().optional(),
    modules_to_save: z.null().optional(),
    bias: z.literal("none"),
    rank_pattern: z.record(z.string(), z.never()).optional(),
    alpha_pattern: z.record(z.string(), z.never()).optional(),
    target_parameters: z.null().optional(),
    auto_mapping: z.null().optional(),
  })
  .passthrough();

const TensorSchema = z.object({
  dtype: z.enum(["F16", "BF16", "F32"]),
  shape: z.array(z.number().int().positive().max(1_000_000)).min(2).max(3),
  data_offsets: z.tuple([
    z.number().int().nonnegative(),
    z.number().int().positive(),
  ]),
});

const parseAdapterJson = (bytes: Uint8Array) => {
  const text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  const value: unknown = JSON.parse(text, (_key: string, item: unknown) => {
    if (typeof item === "number" && !Number.isFinite(item))
      throw new Error("Non-finite JSON number.");
    return item;
  });
  // JSON.parse discards duplicate keys; inspect the original property tokens too.
  const containers: (Set<string> | null)[] = [];
  for (let index = 0; index < text.length; index++) {
    const character = text[index];
    if (character === "{") containers.push(new Set());
    else if (character === "[") containers.push(null);
    else if (character === "}" || character === "]") containers.pop();
    else if (character === '"') {
      let end = index + 1;
      while (end < text.length) {
        if (text[end] === "\\") end += 2;
        else if (text[end] === '"') break;
        else end++;
      }
      let next = end + 1;
      while (/\s/.test(text[next] ?? "") && next < text.length) next++;
      const keys = containers.at(-1);
      if (keys && text[next] === ":") {
        const key = JSON.parse(text.slice(index, end + 1)) as string;
        if (keys.has(key)) throw new Error("Duplicate JSON key.");

        keys.add(key);
      }
      index = end;
    }
  }
  return value;
};

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
  baseConfiguration: BaseModelConfiguration,
) => {
  const layerCount = z
    .number()
    .int()
    .min(1)
    .max(4096)
    .parse(baseConfiguration.layerCount);
  const expertCount = z
    .number()
    .int()
    .min(0)
    .max(4096)
    .parse(baseConfiguration.expertCount);
  const config = ConfigSchema.parse(parseAdapterJson(configBytes));
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
    headerSize > 100_000_000 ||
    headerSize + 8 >= weights.sizeBytes
  )
    throw new Error("Invalid safetensors header.");

  const tensors = z
    .record(z.string(), z.unknown())
    .parse(parseAdapterJson(await weights.read(8, headerSize)));
  const targetModules = new Set(
    config.target_modules.map((module) => module.split(".").at(-1)),
  );
  const layers = new Set<number>();
  const projections = new Set<string>();
  const expertCoverage = new Map<string, Set<number> | null>();
  const expertLayouts = new Set<string>();
  const ranges: [number, number, number, number][] = [];
  const names = Object.keys(tensors).filter((name) => name !== "__metadata__");
  if (!names.length) throw new Error("The adapter contains no tensors.");

  for (const name of names) {
    const tensorName =
      /^(?:[a-zA-Z0-9_]+\.)*layers\.(\d+)\.(.+)\.lora_([AB])\.weight$/.exec(
        name,
      );
    if (!tensorName)
      throw new Error("Only LoRA A/B weight tensors are supported.");

    const layer = Number(tensorName[1]);
    if (layer >= layerCount)
      throw new Error("Adapter layer is outside the base model.");

    layers.add(layer);
    const tensor = TensorSchema.parse(tensors[name]);
    const [start, end] = tensor.data_offsets;
    const width = tensor.dtype === "F32" ? 4 : 2;
    const isA = tensorName[3] === "A";
    const pair = name.replace(
      isA ? ".lora_A" : ".lora_B",
      isA ? ".lora_B" : ".lora_A",
    );
    if (
      tensor.shape[tensor.shape.length - (isA ? 2 : 1)] !== config.r ||
      !(pair in tensors) ||
      end - start !==
        tensor.shape.reduce((size, dimension) => size * dimension, width)
    )
      throw new Error(
        "Adapter tensor ranks, pairs or sizes do not match the config.",
      );

    const moduleName = tensorName[2]!.split(".").at(-1);
    if (!moduleName || !targetModules.has(moduleName))
      throw new Error("Tensor target modules do not match the config.");

    if (baseConfiguration.projectionShapes) {
      const key = `${layer}/${tensorName[2]}`;
      const expected = baseConfiguration.projectionShapes[key];
      if (!expected)
        throw new Error(
          "Adapter target module is not supported by this serving model.",
        );
      if (
        tensor.shape.length !== 2 ||
        tensor.shape[isA ? 1 : 0] !== expected[isA ? 1 : 0]
      )
        throw new Error(
          "Adapter tensor dimensions do not match the serving checkpoint.",
        );
      projections.add(key);
    }

    const expertName = /(?:^|\.)experts\.(\d+)\./.exec(tensorName[2]!);
    const fused = tensor.shape.length === 3;
    if (expertName || fused) {
      expertLayouts.add(fused ? "3d" : "2d");
      if (!expertCount)
        throw new Error("Adapter expert is outside the base model.");

      const key = `${layer}/${moduleName}`;
      if (fused) {
        if (tensor.shape[0] !== expertCount)
          throw new Error(
            "Fused adapter expert count does not match the base model.",
          );
        expertCoverage.set(key, null);
      } else {
        const expert = Number(expertName![1]);
        if (expert >= expertCount)
          throw new Error("Adapter expert is outside the base model.");
        const indices = expertCoverage.get(key) ?? new Set<number>();
        indices.add(expert);
        expertCoverage.set(key, indices);
      }
    }

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
  if (baseConfiguration.projectionShapes) {
    for (const key of Object.keys(baseConfiguration.projectionShapes)) {
      if (targetModules.has(key.split(".").at(-1)!) && !projections.has(key))
        throw new Error(
          "Adapter target module coverage is incomplete for the serving checkpoint.",
        );
    }
  }

  if (layers.size !== layerCount)
    throw new Error("Incomplete adapter layer coverage.");

  if (
    [...expertCoverage.values()].some(
      (indices) => indices !== null && indices.size !== expertCount,
    )
  )
    throw new Error("Incomplete adapter expert coverage.");

  if (expertLayouts.size > 1)
    throw new Error("Mixed adapter expert layouts are unsupported.");

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
