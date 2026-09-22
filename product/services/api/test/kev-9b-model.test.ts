import { ModelPropertiesInputSchema } from "@gradiated/contracts";
import { describe, expect, it } from "vitest";

import {
  createKev9bModelConfiguration,
  kev9bArtifactModelPath,
  kev9bBaseModelPath,
  kev9bModelId,
} from "../src/operations/kev-9b-model.js";

describe("Kev 9B model configuration", () => {
  it("uses the pinned release and the runtime's own input bound", () => {
    const model = createKev9bModelConfiguration();
    expect(model.id).toBe("jaredpalmer/kev-9b");
    expect(kev9bModelId).toBe(model.id);
    expect(kev9bArtifactModelPath).toBe("jaredpalmer/kev-9b");
    expect(kev9bBaseModelPath).toBe("Qwen/Qwen3.5-9B-Base");
    expect(
      model.properties.input_modalities[0]!.supported_inputs.max_context_length
        .value,
    ).toBe(8_192);
  });

  it("prices input only, undercutting the model it reconstructs", () => {
    const properties = createKev9bModelConfiguration().properties;
    expect(properties.input_modalities[0]!.pricing).toEqual([
      { type: "prompt", unit: "token", cost: 30 },
      { type: "cached_prompt", unit: "token", cost: 6 },
    ]);
    // Decisions generate nothing, so output can never contribute a charge.
    expect(properties.output_modalities[0]!.pricing).toEqual([
      { type: "completion", unit: "token", cost: 0 },
    ]);
  });

  it("advertises a decision model rather than a chat model", () => {
    const output =
      createKev9bModelConfiguration().properties.output_modalities[0]!;
    expect(output.streaming).toBe(false);
    expect(output.supported_parameters).toEqual({});
    // The schema demands a positive length; this is the smallest it permits.
    expect(output.max_length.value).toBe(1);
    expect(output.default_length.value).toBe(1);
  });

  it("satisfies the schema the catalog accepts", () => {
    // The catalog fills in schema_version and the projector then validates the
    // normalised record, so the configuration is checked as the input it is.
    const parsed = ModelPropertiesInputSchema.parse(
      createKev9bModelConfiguration().properties,
    );
    expect(parsed.output_modalities[0]!.streaming).toBe(false);
    expect(parsed.input_modalities[0]!.pricing).toContainEqual({
      type: "prompt",
      unit: "token",
      cost: 30,
    });
  });
});
