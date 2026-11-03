import { gunzipSync } from "node:zlib";
import { describe, expect, it } from "vitest";
import {
  adapterArchive,
  validateAdapterFiles,
} from "../src/training/adapter-upload.js";
import { adapterFiles } from "./support/adapter-upload.js";

const base = "test/base";

describe("external adapter validation", () => {
  it("accepts paired LoRA tensors and constructs a deterministic two-file archive", async () => {
    const { config, weights } = adapterFiles(base);
    expect(validateAdapterFiles(config, weights, base).r).toBe(2);
    const archive = await adapterArchive(config, weights);
    expect(await adapterArchive(config, weights)).toEqual(archive);
    const tar = gunzipSync(archive);
    expect(tar.subarray(0, 19).toString()).toBe("adapter_config.json");
    expect(tar.includes(Buffer.from("adapter_model.safetensors"))).toBe(true);
    expect(tar.includes(weights)).toBe(true);
  });
  it("rejects a different base model and malformed safetensors", () => {
    const { config, weights } = adapterFiles(base);
    expect(() => validateAdapterFiles(config, weights, "other/base")).toThrow(
      "base model",
    );
    for (const data of [
      Buffer.alloc(0),
      Buffer.alloc(9, 255),
      weights.subarray(0, weights.length - 1),
    ])
      expect(() => validateAdapterFiles(config, data, base)).toThrow();
  });
  it("rejects NaN and infinity in adapter tensors", () => {
    const { config, weights } = adapterFiles(base);
    const headerSize = Number(weights.readBigUInt64LE());
    weights.writeFloatLE(Number.NaN, 8 + headerSize);
    expect(() => validateAdapterFiles(config, weights, base)).toThrow(
      "non-finite",
    );
    weights.writeFloatLE(Number.POSITIVE_INFINITY, 8 + headerSize);
    expect(() => validateAdapterFiles(config, weights, base)).toThrow(
      "non-finite",
    );
  });
  it("rejects executable weights, rank mismatches, overlapping offsets and unsupported config", () => {
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
    expect(() =>
      validateAdapterFiles(
        config,
        mutate((header) => header.replace("lora_A", "evil")),
        base,
      ),
    ).toThrow();
    expect(() =>
      validateAdapterFiles(
        config,
        mutate((header) => header.replace("[32,64]", "[0,32]")),
        base,
      ),
    ).toThrow();
    expect(() =>
      validateAdapterFiles(
        Buffer.from(config.toString().replace('"r":2', '"r":3')),
        weights,
        base,
      ),
    ).toThrow();
    expect(() =>
      validateAdapterFiles(
        Buffer.from(config.toString().replace('"LORA"', '"OTHER"')),
        weights,
        base,
      ),
    ).toThrow();
  });
});
