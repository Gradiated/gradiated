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

  const cartridge = (has_slot_token_ids: boolean) =>
    version({
      format: "cartridge",
      artifact_uri: "s3://bucket/cartridges/x/cartridge.safetensors",
      sha256: "a".repeat(64),
      size_bytes: 1024,
      num_tokens: 4,
      hidden_size: 8,
      placement: "system_prompt_start",
      separator: "\n\n",
      has_slot_token_ids,
      validated_base_model_revision: "a".repeat(40),
    });

  // Whether a deployment serves cartridges is checked by qualification.
  it("accepts a cartridge with the slot token IDs serving requires", () => {
    expect(() => requireLoadableAdapter(cartridge(true))).not.toThrow();
  });

  it("refuses a cartridge without slot token IDs", () => {
    expect(() => requireLoadableAdapter(cartridge(false))).toThrow(
      "This cartridge has no slot token IDs",
    );
  });
});
