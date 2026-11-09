import {
  ModelPropertiesInputSchema,
  OpenRouterModelIdSchema,
} from "@gradiated/contracts";
import { modelType } from "@gradiated/contracts/model-catalog";
import { describe, expect, it } from "vitest";

import { catalogModels, legacyModels } from "../src/catalog/models/index.js";
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
    "z-ai/glm-5.3-flash": { input: [150, 30], output: [500, 500] },
    "dealignai/glm-5.3-flash-uncensored": {
      input: [100, 10],
      output: [450, 450],
    },
    "jaredpalmer/kev-9b": { input: [30, 6], output: [0] },
    "moonshotai/kimi-k3.1-pro": {
      input: [1_600, 160],
      output: [9_000, 9_000],
    },
    "z-ai/glm-5.3": { input: [1_400, 260], output: [4_400, 4_400] },
  };

  it.each(catalogModels)("pins the nano-USD prices of $id", (model) => {
    const pinned = prices(model);

    expect({
      input: pinned.input.map(({ cost }) => cost),
      output: pinned.output.map(({ cost }) => cost),
    }).toEqual(pinnedPrices[model.id]);
  });

  it("maps only verified exact models to OpenRouter", () => {
    const mappings = Object.fromEntries(
      [...catalogModels, ...legacyModels].map((model) => [
        model.id,
        "openrouterModelId" in model ? model.openrouterModelId : undefined,
      ]),
    );

    expect(mappings).toEqual({
      "deepseek/deepseek-v4.1-flash": "deepseek/deepseek-v4.1-flash",
      "z-ai/glm-5.3-flash": "z-ai/glm-5.3-flash",
      "dealignai/glm-5.3-flash-uncensored": null,
      "dealignai/glm-5.3-flash-uncensored-nvfp4": null,
      "jaredpalmer/kev-9b": undefined,
      "moonshotai/kimi-k3.1-pro": null,
      "z-ai/glm-5.3": "z-ai/glm-5.3",
    });
    for (const mapping of Object.values(mappings)) {
      if (typeof mapping === "string") OpenRouterModelIdSchema.parse(mapping);
    }
  });

  it("rejects an OpenRouter variant or moving alias as a mapping", () => {
    for (const mapping of [
      "z-ai/glm-5.3-flash:free",
      "~z-ai/glm-latest",
      "Z-AI/GLM-5.3-Flash",
      "glm-5.3-flash",
    ]) {
      expect(OpenRouterModelIdSchema.safeParse(mapping).success).toBe(false);
    }
  });

  it("advertises Kev 9B as a decision model that cannot generate", () => {
    expect(createKev9bModelConfiguration().status).toBe("available");
    expect(modelType(createKev9bModelConfiguration().id)).toBe("decision");
    const [output] =
      createKev9bModelConfiguration().properties.output_modalities;

    expect(output).toMatchObject({
      streaming: false,
      supported_parameters: {},
      max_length: { value: 1 },
      pricing: [{ type: "completion", cost: 0 }],
    });
  });

  it("classifies the generation models as chat", () => {
    expect(catalogModels.map((model) => modelType(model.id))).toEqual([
      "chat",
      "chat",
      "chat",
      "decision",
      "chat",
      "chat",
    ]);
  });

  it("advertises the GLM effort parameter so the gateway forwards it to the runtime", () => {
    const glm = catalogModels.find(
      (model) => model.id === "z-ai/glm-5.3-flash",
    );
    const properties = ModelPropertiesInputSchema.parse(glm?.properties);

    expect(glm?.status).toBe("available");

    expect(
      properties.output_modalities[0]?.supported_parameters.reasoning_effort,
    ).toEqual({
      type: "enum",
      values: ["low", "high", "max"],
    });
  });
});

it("offers Kimi on local capacity and advertises its exact reasoning contract", () => {
  const model = catalogModels.find(
    (item) => item.id === "moonshotai/kimi-k3.1-pro",
  );

  expect(model?.status).toBe("available");
  expect(
    model && "openrouterModelId" in model ? model.openrouterModelId : undefined,
  ).toBeNull();
  expect(model?.properties).toMatchObject({
    hugging_face_id: "moonshotai/Kimi-K3.1-Pro",
    quantization: "mxfp4",
    input_modalities: [{ type: "text" }],
    reasoning: {
      supported_efforts: ["low", "high", "max"],
      default_effort: "max",
    },
    output_modalities: [
      {
        supported_parameters: {
          reasoning_effort: { type: "enum", values: ["low", "high", "max"] },
        },
      },
    ],
  });
});

it("identifies Dealign weights separately from the stock training base", () => {
  const model = catalogModels.find(
    (item) => item.id === "dealignai/glm-5.3-flash-uncensored",
  );

  expect(model?.status).toBe("available");
  expect(model?.properties).toMatchObject({
    hugging_face_id: "dealignai/GLM-5.3-Flash-UNCENSORED-NVFP4",
    quantization: "nvfp4",
  });
});
