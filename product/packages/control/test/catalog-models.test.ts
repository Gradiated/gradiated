import { ModelPropertiesInputSchema } from "@gradiated/contracts";
import { describe, expect, it } from "vitest";

import { catalogModels } from "../src/catalog/models/index.js";
import { createKev9bModelConfiguration } from "../src/catalog/models/kev-9b.js";

const prices = (model: { properties: unknown }) => {
  const properties = ModelPropertiesInputSchema.parse(model.properties);

  return {
    input: properties.input_modalities.flatMap((modality) => modality.pricing),
    output: properties.output_modalities.flatMap(
      (modality) => modality.pricing,
    ),
  };
};

describe("model configurations", () => {
  it.each(catalogModels)("$id is a valid catalog model", (model) => {
    const properties = ModelPropertiesInputSchema.parse(model.properties);

    expect(model.id).toBe(model.id.toLowerCase());
    for (const output of properties.output_modalities) {
      expect(output.default_length?.value ?? 0).toBeLessThanOrEqual(
        output.max_length.value,
      );
    }
    const { input, output } = prices(model);
    for (const { cost } of [...input, ...output]) {
      expect(Number.isSafeInteger(cost) && cost >= 0).toBe(true);
    }
  });

  const pinnedPrices: Record<string, { input: number[]; output: number[] }> = {
    "deepseek/deepseek-v4.1-flash": { input: [300, 6], output: [1_200, 1_200] },
    "z-ai/glm-5.3-flash": { input: [75, 15], output: [250, 250] },
    "jaredpalmer/kev-9b": { input: [30, 6], output: [0] },
  };

  it.each(catalogModels)("pins the nano-USD prices of $id", (model) => {
    const pinned = prices(model);

    expect({
      input: pinned.input.map(({ cost }) => cost),
      output: pinned.output.map(({ cost }) => cost),
    }).toEqual(pinnedPrices[model.id]);
  });

  it("advertises Kev 9B as a decision model that cannot generate", () => {
    const [output] =
      createKev9bModelConfiguration().properties.output_modalities;

    expect(output).toMatchObject({
      streaming: false,
      supported_parameters: {},
      max_length: { value: 1 },
      pricing: [{ type: "completion", cost: 0 }],
    });
  });
});
