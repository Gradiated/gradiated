import { describe, expect, it } from "vitest";

import {
  createDeepseekV4FlashModelConfiguration,
  deepseekV4FlashArtifactModelPath,
  deepseekV4FlashModelId,
} from "../src/operations/deepseek-v4-flash-model.js";

describe("DeepSeek V4 Flash model configuration", () => {
  it("uses the production release and measured runtime limits", () => {
    const model = createDeepseekV4FlashModelConfiguration();
    const input = model.properties.input_modalities[0]!;
    const output = model.properties.output_modalities[0]!;

    expect(model.id).toBe("deepseek/deepseek-v4-flash-0731");
    expect(model.id).toBe(model.id.toLowerCase());
    expect(deepseekV4FlashModelId).toBe(model.id);
    expect(deepseekV4FlashArtifactModelPath).toBe(
      "deepseek-ai/DeepSeek-V4-Flash-0731",
    );
    expect(input.supported_inputs.max_context_length.value).toBe(262_144);
    expect(output.max_length.value).toBe(32_768);
  });

  it("publishes the selected prices and OpenAI-compatible parameters", () => {
    const properties = createDeepseekV4FlashModelConfiguration().properties;
    const input = properties.input_modalities[0]!;
    const output = properties.output_modalities[0]!;

    expect(input.pricing).toEqual([
      { type: "prompt", unit: "token", cost: 60 },
      { type: "cached_prompt", unit: "token", cost: 12 },
    ]);
    expect(output.pricing).toEqual([
      { type: "completion", unit: "token", cost: 120 },
      { type: "internal_reasoning", unit: "token", cost: 120 },
    ]);
    expect(output.supported_parameters).toHaveProperty("temperature");
    expect(output.supported_parameters).toHaveProperty("stop");
    expect(output.supported_parameters).not.toHaveProperty("tools");
    expect(output.supported_parameters).not.toHaveProperty("reasoning");
  });
});
