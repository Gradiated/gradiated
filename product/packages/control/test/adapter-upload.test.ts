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
) =>
  validate(
    config,
    {
      sizeBytes: weights.length,
      read: async (offset, length) => weights.subarray(offset, offset + length),
    },
    model,
  );

describe("external adapter validation", () => {
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
      const dimensions = Math.floor((MAX_ADAPTER_BYTES - 4096) / 16);
      const payloadSize = dimensions * 16;
      const header = Buffer.from(
        JSON.stringify({
          "base_model.model.layers.0.self_attn.q_proj.lora_A.weight": {
            dtype: "F32",
            shape: [2, dimensions],
            data_offsets: [0, payloadSize / 2],
          },
          "base_model.model.layers.0.self_attn.q_proj.lora_B.weight": {
            dtype: "F32",
            shape: [dimensions, 2],
            data_offsets: [payloadSize / 2, payloadSize],
          },
        }),
      );
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
        expect(sizeBytes).toBeGreaterThan(MAX_ADAPTER_BYTES - 4096);
        const reader = adapterFileReader(file, sizeBytes);
        expect(
          (await validate(adapterFiles(base).config, reader, base)).r,
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
