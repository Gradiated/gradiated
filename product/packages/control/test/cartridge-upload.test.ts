import { createHash } from "node:crypto";
import { mkdtemp, open, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { validateCartridgeFile } from "../src/training/cartridge-upload.js";
import { cartridgeFile as safetensors, NAN_BF16 } from "./support/cartridge.js";

describe("validateCartridgeFile", () => {
  let directory: string;
  beforeAll(async () => {
    directory = await mkdtemp(join(tmpdir(), "cartridge-test-"));
  });
  afterAll(() => rm(directory, { recursive: true, force: true }));

  const validate = async (
    bytes: Buffer,
    expected = { hiddenSize: 8, maxTokens: 16, vocabSize: 1000 },
  ) => {
    const path = join(directory, `${Math.random()}.safetensors`);
    await writeFile(path, bytes);
    const file = await open(path, "r");
    try {
      return await validateCartridgeFile(file, bytes.length, expected);
    } finally {
      await file.close();
    }
  };

  it("accepts a cartridge and reports its shape and hash", async () => {
    const bytes = safetensors({
      metadata: { format: "gradiated.cartridge/1", separator: "\n" },
    });

    expect(await validate(bytes)).toEqual({
      numTokens: 4,
      hiddenSize: 8,
      separator: "\n",
      hasSlotTokenIds: true,
      sha256: createHash("sha256").update(bytes).digest("hex"),
    });
  });

  it("accepts a cartridge without slot token IDs", async () => {
    expect(await validate(safetensors({ slots: false }))).toMatchObject({
      hasSlotTokenIds: false,
      separator: "\n\n",
    });
  });

  it.each([
    [
      "one that fills the context",
      safetensors({ tokens: 16 }),
      "context holds 16 tokens",
    ],
    ["the wrong width", safetensors({ hidden: 4 }), "must be 8 wide"],
    ["non-finite values", safetensors({ value: NAN_BF16 }), "must be finite"],
    [
      "missing metadata",
      safetensors({ metadata: {} }),
      "format to gradiated.cartridge/1",
    ],
    ["extra tensors", safetensors({ extra: true }), "only contain embeddings"],
    [
      "out-of-vocabulary slots",
      safetensors({ slots: [1, 2, 3, 5000] }),
      "vocabulary",
    ],
    [
      "mismatched slot count",
      safetensors({ slots: [1, 2] }),
      "one ID per cartridge position",
    ],
    [
      "a cut-off header",
      safetensors().subarray(0, 40),
      "header length is invalid",
    ],
    [
      "cut-off tensor data",
      safetensors({ slots: false }).subarray(0, -4),
      "does not match its shape",
    ],
    [
      "non-text metadata",
      safetensors({
        metadata: { format: "gradiated.cartridge/1", steps: 300 } as never,
      }),
      "metadata values must all be text",
    ],
    [
      "trailing bytes after the tensors",
      Buffer.concat([safetensors(), Buffer.alloc(4)]),
      "contiguous and fill the file",
    ],
  ])("rejects %s", async (_, bytes, message) => {
    await expect(validate(bytes)).rejects.toThrow(message);
  });
});
