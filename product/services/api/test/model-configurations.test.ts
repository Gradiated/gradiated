import { ModelPropertiesInputSchema } from "@gradiated/contracts";
import { describe, expect, it } from "vitest";

import {
  createDeepseekV41FlashModelConfiguration,
  deepseekV41FlashModelId,
} from "../src/operations/deepseek-v4-1-flash-model.js";
import {
  createDeepseekV4FlashModelConfiguration,
  deepseekV4FlashModelId,
} from "../src/operations/deepseek-v4-flash-model.js";
import {
  createGemma4ModelConfiguration,
  gemma4ModelId,
} from "../src/operations/gemma4-model.js";
import {
  createGlm53FlashModelConfiguration,
  glm53FlashModelId,
} from "../src/operations/glm-5-3-flash-model.js";
import {
  createKev9bModelConfiguration,
  kev9bModelId,
} from "../src/operations/kev-9b-model.js";

const configurations = [
  {
    id: deepseekV41FlashModelId,
    create: createDeepseekV41FlashModelConfiguration,
  },
  {
    id: deepseekV4FlashModelId,
    create: createDeepseekV4FlashModelConfiguration,
  },
  { id: gemma4ModelId, create: createGemma4ModelConfiguration },
  { id: glm53FlashModelId, create: createGlm53FlashModelConfiguration },
  { id: kev9bModelId, create: createKev9bModelConfiguration },
];

const prices = (create: () => { properties: unknown }) => {
  const properties = ModelPropertiesInputSchema.parse(create().properties);

  return {
    input: properties.input_modalities.flatMap((modality) => modality.pricing),
    output: properties.output_modalities.flatMap(
      (modality) => modality.pricing,
    ),
  };
};

describe("model configurations", () => {
  it.each(configurations)("$id is a valid catalog model", ({ id, create }) => {
    const model = create();
    const properties = ModelPropertiesInputSchema.parse(model.properties);

    expect(model.id).toBe(id);
    expect(model.id).toBe(model.id.toLowerCase());
    for (const output of properties.output_modalities) {
      expect(output.default_length?.value ?? 0).toBeLessThanOrEqual(
        output.max_length.value,
      );
    }
    const { input, output } = prices(create);
    for (const { cost } of [...input, ...output]) {
      expect(Number.isSafeInteger(cost) && cost >= 0).toBe(true);
    }
  });

  it.each([
    {
      create: createDeepseekV41FlashModelConfiguration,
      input: [300, 6],
      output: [1_200, 1_200],
    },
    {
      create: createDeepseekV4FlashModelConfiguration,
      input: [60, 12],
      output: [120, 120],
    },
    { create: createGemma4ModelConfiguration, input: [80, 10], output: [350] },
    {
      create: createGlm53FlashModelConfiguration,
      input: [75, 15],
      output: [250, 250],
    },
    { create: createKev9bModelConfiguration, input: [30, 6], output: [0] },
  ])(
    "pins the nano-USD prices of $create.name",
    ({ create, input, output }) => {
      const pinned = prices(create);

      expect(pinned.input.map(({ cost }) => cost)).toEqual(input);
      expect(pinned.output.map(({ cost }) => cost)).toEqual(output);
    },
  );

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
