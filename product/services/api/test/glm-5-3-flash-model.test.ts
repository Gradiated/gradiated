import { describe, expect, it } from "vitest";

import {
  createGlm53FlashModelConfiguration,
  glm53FlashArtifactModelPath,
  glm53FlashModelId,
} from "../src/operations/glm-5-3-flash-model.js";

describe("GLM-5.3 Flash model configuration", () => {
  it("uses the pinned release and advertised limits", () => {
    const model = createGlm53FlashModelConfiguration();
    expect(model.id).toBe("z-ai/glm-5.3-flash");
    expect(glm53FlashModelId).toBe(model.id);
    expect(glm53FlashArtifactModelPath).toBe("zai-org/GLM-5.3-Flash");
    expect(
      model.properties.input_modalities[0]!.supported_inputs.max_context_length
        .value,
    ).toBe(1_048_576);
    expect(model.properties.output_modalities[0]!.max_length.value).toBe(
      131_072,
    );
  });

  it("publishes the direct half-price rates", () => {
    const properties = createGlm53FlashModelConfiguration().properties;
    expect(properties.input_modalities[0]!.pricing).toEqual([
      { type: "prompt", unit: "token", cost: 75 },
      { type: "cached_prompt", unit: "token", cost: 15 },
    ]);
    expect(properties.output_modalities[0]!.pricing).toEqual([
      { type: "completion", unit: "token", cost: 250 },
      { type: "internal_reasoning", unit: "token", cost: 250 },
    ]);
  });
});
