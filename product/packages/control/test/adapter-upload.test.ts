import { gunzipSync } from "node:zlib";
import { mkdtemp, open, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createHash, randomFillSync } from "node:crypto";
import { describe, expect, it } from "vitest";
import { MAX_ADAPTER_BYTES } from "@gradiated/contracts";
import {
  adapterArchive,
  adapterFileReader,
  validateAdapterFiles as validate,
} from "../src/training/adapter-upload.js";
import { adapterFiles } from "./support/adapter-upload.js";

const base = "test/base";
const validateAdapterFiles = (
  config: Uint8Array,
  weights: Buffer,
  model: string,
  layerCount = 1,
  expertCount = 0,
) =>
  validate(
    config,
    {
      sizeBytes: weights.length,
      read: async (offset, length) => weights.subarray(offset, offset + length),
    },
    model,
    { layerCount, expertCount },
  );

const headFiles = (prefix = "base_model.model.") => {
  const config = Buffer.from(
    JSON.stringify({
      peft_type: "LORA",
      task_type: "CAUSAL_LM",
      base_model_name_or_path: base,
      r: 2,
      lora_alpha: 4,
      target_modules: ["lm_head"],
      bias: "none",
    }),
  );
  const header = Buffer.from(
    JSON.stringify({
      [`${prefix}lm_head.lora_A.weight`]: {
        dtype: "F32",
        shape: [2, 4],
        data_offsets: [0, 32],
      },
      [`${prefix}lm_head.lora_B.weight`]: {
        dtype: "F32",
        shape: [8, 2],
        data_offsets: [32, 96],
      },
    }),
  );
  const size = Buffer.alloc(8);
  size.writeBigUInt64LE(BigInt(header.length));
  const weights = Buffer.concat([size, header, Buffer.alloc(96)]);
  return {
    config,
    weights,
    reader: {
      sizeBytes: weights.length,
      read: async (offset: number, length: number) =>
        weights.subarray(offset, offset + length),
    },
  };
};

describe("external adapter validation", () => {
  it.each(["base_model.model.", ""])(
    "accepts a head adapter only with pinned head dimensions (%s)",
    async (prefix) => {
      const f = headFiles(prefix);
      expect(
        (
          await validate(f.config, f.reader, base, {
            layerCount: 1,
            expertCount: 0,
            projectionShapes: { lm_head: [8, 4] },
          })
        ).r,
      ).toBe(2);
    },
  );
  it.each(["model.lm_head", "base_model.model.lm_head"])(
    "rejects a noncanonical head target %s before publication",
    async (target) => {
      const f = headFiles();
      const config = Buffer.from(
        JSON.stringify({
          ...JSON.parse(f.config.toString()),
          target_modules: [target],
        }),
      );
      await expect(
        validate(config, f.reader, base, {
          layerCount: 1,
          expertCount: 0,
          projectionShapes: { lm_head: [8, 4] },
        }),
      ).rejects.toThrow("not supported");
    },
  );
  it("rejects unqualified heads, incorrect vocabulary dimensions, and layer-local head aliases", async () => {
    const f = headFiles();
    for (const shapes of [
      undefined,
      {},
      { lm_head: [7, 4] as const },
      { lm_head: [8, 5] as const },
    ]) {
      await expect(
        validate(f.config, f.reader, base, {
          layerCount: 1,
          expertCount: 0,
          ...(shapes ? { projectionShapes: shapes } : {}),
        }),
      ).rejects.toThrow("serving");
    }
    const spoof = headFiles("base_model.model.layers.0.");
    await expect(
      validate(spoof.config, spoof.reader, base, {
        layerCount: 1,
        expertCount: 0,
        projectionShapes: { lm_head: [8, 4], "0/lm_head": [8, 4] },
      }),
    ).rejects.toThrow("not supported");
  });

  it("rejects side markers embedded in module paths", async () => {
    const files = adapterFiles(base);
    const size = Number(files.weights.readBigUInt64LE());
    const header = Buffer.from(
      files.weights
        .subarray(8, 8 + size)
        .toString()
        .replaceAll("self_attn.q_proj", "self_attn.lora_A.q_proj"),
    );
    const prefix = Buffer.alloc(8);
    prefix.writeBigUInt64LE(BigInt(header.length));
    await expect(
      validateAdapterFiles(
        files.config,
        Buffer.concat([prefix, header, files.weights.subarray(8 + size)]),
        base,
      ),
    ).rejects.toThrow("Side markers");
  });
  it.each([1, 2, 8, 16, 32])("accepts upload rank %i", async (rank) => {
    const { config, weights } = adapterFiles(base, 1, undefined, rank);
    expect((await validateAdapterFiles(config, weights, base)).r).toBe(rank);
  });
  it.each([33, 64])("rejects upload rank %i above the cap", async (rank) => {
    const { config, weights } = adapterFiles(base, 1, undefined, rank);
    await expect(validateAdapterFiles(config, weights, base)).rejects.toThrow();
  });
  it("accepts paired LoRA tensors and constructs a deterministic two-file archive", async () => {
    const { config, weights } = adapterFiles(base);
    expect((await validateAdapterFiles(config, weights, base)).r).toBe(2);
    const directory = await mkdtemp(join(tmpdir(), "adapter-test-"));
    try {
      const path = join(directory, "weights");
      await writeFile(path, weights);
      const first = await adapterArchive(
        config,
        path,
        weights.length,
        join(directory, "first.gz"),
      );
      const second = await adapterArchive(
        config,
        path,
        weights.length,
        join(directory, "second.gz"),
      );
      expect(second).toEqual(first);
      const archive = await readFile(join(directory, "first.gz"));
      expect(createHash("sha256").update(archive).digest("hex")).toBe(
        first.sha256,
      );
      expect(archive.length).toBe(first.sizeBytes);
      const tar = gunzipSync(archive);
      expect(tar.subarray(0, 19).toString()).toBe("adapter_config.json");
      expect(tar.includes(Buffer.from("adapter_model.safetensors"))).toBe(true);
      expect(tar.includes(weights)).toBe(true);
    } finally {
      await rm(directory, { recursive: true, force: true });
    }
  });
  it("rejects a different base model and malformed safetensors", async () => {
    const { config, weights } = adapterFiles(base);
    await expect(
      validateAdapterFiles(config, weights, "other/base"),
    ).rejects.toThrow("base model");
    for (const data of [
      Buffer.alloc(0),
      Buffer.alloc(9, 255),
      weights.subarray(0, weights.length - 1),
    ])
      await expect(validateAdapterFiles(config, data, base)).rejects.toThrow();
  });
  it("rejects tensor names the serving runtime cannot materialize", async () => {
    const { config, weights } = adapterFiles(base);
    const size = Number(weights.readBigUInt64LE());
    const rewrite = (convert: (name: string) => string) => {
      const original = JSON.parse(weights.subarray(8, 8 + size).toString());
      const header = Buffer.from(
        JSON.stringify(
          Object.fromEntries(
            Object.entries(original).map(([name, value]) => [
              convert(name),
              value,
            ]),
          ),
        ),
      );
      const prefix = Buffer.alloc(8);
      prefix.writeBigUInt64LE(BigInt(header.length));
      return Buffer.concat([prefix, header, weights.subarray(8 + size)]);
    };
    await expect(
      validateAdapterFiles(
        config,
        rewrite((name) =>
          name.replace(/\.lora_([AB])\.weight$/, ".lora_$1.default.weight"),
        ),
        base,
      ),
    ).rejects.toThrow("Only LoRA A/B");
    await expect(
      validateAdapterFiles(
        config,
        rewrite((name) => name.replace("layers.0.", "")),
        base,
      ),
    ).rejects.toThrow("Only LoRA A/B");
    await expect(
      validateAdapterFiles(
        config,
        rewrite((name) => name.replace("base_model.", "base-model.")),
        base,
      ),
    ).rejects.toThrow("Only LoRA A/B");
  });
  it("accepts a subset of base layers and rejects out-of-range layers", async () => {
    const full = adapterFiles(base, 2);
    expect(
      (await validateAdapterFiles(full.config, full.weights, base, 2)).r,
    ).toBe(2);
    const partial = adapterFiles(base);
    expect(
      (await validateAdapterFiles(partial.config, partial.weights, base, 2)).r,
    ).toBe(2);
    const outOfRange = Buffer.from(partial.weights);
    const size = Number(outOfRange.readBigUInt64LE());
    const header = outOfRange
      .subarray(8, 8 + size)
      .toString()
      .replaceAll("layers.0.", "layers.2.");
    outOfRange.write(header, 8);
    await expect(
      validateAdapterFiles(partial.config, outOfRange, base, 2),
    ).rejects.toThrow("outside the base model");
  });
  it("requires complete expert coverage and rejects expert indices outside the base", async () => {
    const full = adapterFiles(base, 2, [0, 1]);
    expect(
      (await validateAdapterFiles(full.config, full.weights, base, 2, 2)).r,
    ).toBe(2);
    const partial = adapterFiles(base, 2, [0]);
    await expect(
      validateAdapterFiles(partial.config, partial.weights, base, 2, 2),
    ).rejects.toThrow("Incomplete adapter expert coverage");
    const outOfRange = adapterFiles(base, 1, [2]);
    await expect(
      validateAdapterFiles(outOfRange.config, outOfRange.weights, base, 1, 2),
    ).rejects.toThrow("outside the base model");
    await expect(
      validateAdapterFiles(partial.config, partial.weights, base, 2, 0),
    ).rejects.toThrow("outside the base model");
  });
  it("rejects headers above the API memory limit before reading metadata", async () => {
    const { config } = adapterFiles(base);
    const headerSize = 8 * 1024 * 1024 + 1;
    const prefix = Buffer.alloc(8);
    prefix.writeBigUInt64LE(BigInt(headerSize));
    const reads: number[] = [];
    await expect(
      validate(
        config,
        {
          sizeBytes: headerSize + 16,
          read: async (offset, length) => {
            reads.push(offset);
            expect(length).toBe(8);
            return prefix;
          },
        },
        base,
        { layerCount: 1, expertCount: 0 },
      ),
    ).rejects.toThrow("Invalid safetensors header");
    expect(reads).toEqual([0]);
  });
  it("caps dimensions before reading tensor data", async () => {
    const header = Buffer.from(
      JSON.stringify({
        "base_model.model.layers.0.self_attn.q_proj.lora_A.weight": {
          dtype: "F32",
          shape: [2, 1000001],
          data_offsets: [0, 8000008],
        },
        "base_model.model.layers.0.self_attn.q_proj.lora_B.weight": {
          dtype: "F32",
          shape: [1000001, 2],
          data_offsets: [8000008, 16000016],
        },
      }),
    );
    const prefix = Buffer.alloc(8);
    prefix.writeBigUInt64LE(BigInt(header.length));
    await expect(
      validate(
        adapterFiles(base).config,
        {
          sizeBytes: 8 + header.length + 16000016,
          read: async (offset) => {
            if (offset === 0) return prefix;
            if (offset === 8) return header;
            throw new Error("Tensor payload must not be read.");
          },
        },
        base,
        { layerCount: 1, expertCount: 0 },
      ),
    ).rejects.toThrow("1000000");
  });
  it("rejects NaN and infinity in adapter tensors", async () => {
    const { config, weights } = adapterFiles(base);
    const headerSize = Number(weights.readBigUInt64LE());
    weights.writeFloatLE(Number.NaN, 8 + headerSize);
    await expect(validateAdapterFiles(config, weights, base)).rejects.toThrow(
      "non-finite",
    );
    weights.writeFloatLE(Number.POSITIVE_INFINITY, 8 + headerSize);
    await expect(validateAdapterFiles(config, weights, base)).rejects.toThrow(
      "non-finite",
    );
  });
  it("rejects executable weights, rank mismatches, overlapping offsets and unsupported config", async () => {
    const { config, weights } = adapterFiles(base);
    const size = Number(weights.readBigUInt64LE());
    const mutate = (replace: (header: string) => string) => {
      const header = Buffer.from(
        replace(weights.subarray(8, 8 + size).toString()),
      );
      const length = Buffer.alloc(8);
      length.writeBigUInt64LE(BigInt(header.length));
      return Buffer.concat([length, header, weights.subarray(8 + size)]);
    };
    await expect(
      validateAdapterFiles(
        config,
        mutate((header) => header.replace("lora_A", "evil")),
        base,
      ),
    ).rejects.toThrow();
    await expect(
      validateAdapterFiles(
        config,
        mutate((header) => header.replace("[32,64]", "[0,32]")),
        base,
      ),
    ).rejects.toThrow();
    await expect(
      validateAdapterFiles(
        Buffer.from(config.toString().replace('"r":2', '"r":3')),
        weights,
        base,
      ),
    ).rejects.toThrow();
    await expect(
      validateAdapterFiles(
        Buffer.from(config.toString().replace('"LORA"', '"OTHER"')),
        weights,
        base,
      ),
    ).rejects.toThrow();
  });
  it("validates and archives a near-limit incompressible adapter with bounded memory", async () => {
    const directory = await mkdtemp(join(tmpdir(), "adapter-limit-test-"));
    const baseline = process.memoryUsage().rss;
    let peak = baseline;
    const sample = setInterval(() => {
      peak = Math.max(peak, process.memoryUsage().rss);
    }, 10);
    try {
      const layerCount = 64;
      const dimensions = Math.floor(
        (MAX_ADAPTER_BYTES - 32768) / (16 * layerCount),
      );
      const bytesPerLayer = dimensions * 16;
      const payloadSize = bytesPerLayer * layerCount;
      const tensors = Object.fromEntries(
        Array.from({ length: layerCount }, (_, layer) => [
          [
            `base_model.model.layers.${layer}.self_attn.q_proj.lora_A.weight`,
            {
              dtype: "F32",
              shape: [2, dimensions],
              data_offsets: [
                layer * bytesPerLayer,
                layer * bytesPerLayer + bytesPerLayer / 2,
              ],
            },
          ],
          [
            `base_model.model.layers.${layer}.self_attn.q_proj.lora_B.weight`,
            {
              dtype: "F32",
              shape: [dimensions, 2],
              data_offsets: [
                layer * bytesPerLayer + bytesPerLayer / 2,
                (layer + 1) * bytesPerLayer,
              ],
            },
          ],
        ]).flat(),
      );
      const header = Buffer.from(JSON.stringify(tensors));
      const prefix = Buffer.alloc(8);
      prefix.writeBigUInt64LE(BigInt(header.length));
      const path = join(directory, "weights");
      const file = await open(path, "wx+");
      try {
        await file.writeFile(prefix);
        await file.writeFile(header);
        const chunk = randomFillSync(Buffer.alloc(64 * 1024));
        for (let offset = 3; offset < chunk.length; offset += 4)
          chunk[offset] = chunk[offset]! & 0x7e;
        for (let offset = 0; offset < payloadSize; offset += chunk.length)
          await file.writeFile(
            chunk.subarray(0, Math.min(chunk.length, payloadSize - offset)),
          );

        const sizeBytes = payloadSize + header.length + 8;
        expect(sizeBytes).toBeLessThanOrEqual(MAX_ADAPTER_BYTES);
        expect(sizeBytes).toBeGreaterThan(MAX_ADAPTER_BYTES - 32768);
        const reader = adapterFileReader(file, sizeBytes);
        expect(
          (
            await validate(adapterFiles(base).config, reader, base, {
              layerCount,
              expertCount: 0,
            })
          ).r,
        ).toBe(2);
        const artifact = await adapterArchive(
          adapterFiles(base).config,
          path,
          sizeBytes,
          join(directory, "archive.gz"),
        );
        expect(artifact.sizeBytes).toBeGreaterThan(MAX_ADAPTER_BYTES * 0.9);
        expect(peak - baseline).toBeLessThan(192 * 1024 * 1024);
      } finally {
        await file.close();
      }
    } finally {
      clearInterval(sample);
      await rm(directory, { recursive: true, force: true });
    }
  }, 60_000);
});
