import { describe, expect, it } from "vitest";
import { requireLoadableAdapter } from "../src/training/hosting.js";
import type { TaskVersionRecord } from "../src/training/records.js";
import { trainingAdapter } from "./support/training.js";

const version = (adapter: TaskVersionRecord["adapter"]) =>
  ({ adapter }) as TaskVersionRecord;

describe("requireLoadableAdapter", () => {
  it("accepts a LoRA adapter with a base revision", () => {
    expect(() =>
      requireLoadableAdapter(
        version({
          ...trainingAdapter,
          validated_base_model_revision: "a".repeat(40),
        }),
      ),
    ).not.toThrow();
  });

  it("refuses cartridges until they can be served", () => {
    expect(() =>
      requireLoadableAdapter(
        version({
          format: "cartridge",
          artifact_uri: "s3://bucket/cartridges/x/cartridge.safetensors",
          sha256: "a".repeat(64),
          size_bytes: 1024,
          num_tokens: 4,
          hidden_size: 8,
          placement: "system_prompt_start",
          separator: "\n\n",
          has_slot_token_ids: false,
          validated_base_model_revision: "a".repeat(40),
        }),
      ),
    ).toThrow("Cartridge versions cannot be served yet.");
  });
});
