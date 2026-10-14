import { describe, expect, it } from "vitest";

import {
  ModelPropertiesInputSchema,
  ModelPropertiesSchema,
  ModelSchema,
  ExternalModelSchema,
  type ModelPropertiesInput,
} from "../src/index.js";

const modelPropertiesInput = (
  overrides: Partial<ModelPropertiesInput> = {},
): ModelPropertiesInput => ({
  description: "Small model.",
  input_modalities: [
    {
      type: "text",
      supported_inputs: {
        max_context_length: { value: 512, unit: "token" },
      },
      pricing: [{ type: "prompt", unit: "token", cost: 0 }],
    },
  ],
  output_modalities: [
    {
      type: "text",
      max_length: { value: 512, unit: "token" },
      pricing: [{ type: "completion", unit: "token", cost: 0 }],
    },
  ],
  ...overrides,
});

type InputModality = ModelPropertiesInput["input_modalities"][number];
type OutputModality = ModelPropertiesInput["output_modalities"][number];

const withModalities = ({
  input = {},
  output = {},
}: {
  input?: Partial<InputModality>;
  output?: Partial<OutputModality>;
}): ModelPropertiesInput => {
  const properties = modelPropertiesInput();

  return {
    ...properties,
    input_modalities: properties.input_modalities.map((modality) => ({
      ...modality,
      ...input,
    })),
    output_modalities: properties.output_modalities.map((modality) => ({
      ...modality,
      ...output,
    })),
  };
};

const parseModalities = (properties: ModelPropertiesInput) => {
  const {
    input_modalities: [input],
    output_modalities: [output],
  } = ModelPropertiesInputSchema.parse(properties);

  return { input, output };
};

describe("ModelPropertiesInputSchema", () => {
  it("defaults cached prompt pricing to the prompt cost", () => {
    const { input } = parseModalities(
      withModalities({
        input: { pricing: [{ type: "prompt", unit: "token", cost: 7 }] },
      }),
    );

    expect(input?.pricing).toEqual([
      { type: "prompt", unit: "token", cost: 7 },
      { type: "cached_prompt", unit: "token", cost: 7 },
    ]);
  });

  it("defaults max_prompt_length to max_context_length", () => {
    const { input } = parseModalities(modelPropertiesInput());

    expect(input?.supported_inputs.max_prompt_length).toEqual({
      value: 512,
      unit: "token",
    });
  });

  it.each([
    [512, 512],
    [4_096, 1_024],
  ])("defaults default_length for max_length %i to %i", (maxLength, value) => {
    const { output } = parseModalities(
      withModalities({
        output: { max_length: { value: maxLength, unit: "token" } },
      }),
    );

    expect(output?.default_length).toEqual({ value, unit: "token" });
  });

  it("prices internal reasoning at the completion cost when reasoning is supported", () => {
    const { output } = parseModalities(
      withModalities({
        output: {
          supported_parameters: { reasoning: { type: "boolean" } },
          pricing: [{ type: "completion", unit: "token", cost: 9 }],
        },
      }),
    );

    expect(output?.pricing).toEqual([
      { type: "completion", unit: "token", cost: 9 },
      { type: "internal_reasoning", unit: "token", cost: 9 },
    ]);
  });

  it("keeps an explicit internal reasoning price", () => {
    const { output } = parseModalities(
      withModalities({
        output: {
          supported_parameters: { reasoning: { type: "boolean" } },
          pricing: [
            { type: "completion", unit: "token", cost: 9 },
            { type: "internal_reasoning", unit: "token", cost: 3 },
          ],
        },
      }),
    );

    expect(output?.pricing).toContainEqual({
      type: "internal_reasoning",
      unit: "token",
      cost: 3,
    });
  });

  it("defaults streaming to true", () => {
    expect(parseModalities(modelPropertiesInput()).output?.streaming).toBe(
      true,
    );
  });

  it("normalizes the pricing order", () => {
    const { input, output } = parseModalities(
      withModalities({
        input: {
          pricing: [
            { type: "cache_write", unit: "token", cost: 3 },
            { type: "cached_prompt", unit: "token", cost: 2 },
            { type: "prompt", unit: "token", cost: 1 },
          ],
        },
        output: {
          pricing: [
            { type: "internal_reasoning", unit: "token", cost: 5 },
            { type: "completion", unit: "token", cost: 4 },
          ],
        },
      }),
    );

    expect(input?.pricing.map(({ type }) => type)).toEqual([
      "prompt",
      "cached_prompt",
      "cache_write",
    ]);
    expect(output?.pricing.map(({ type }) => type)).toEqual([
      "completion",
      "internal_reasoning",
    ]);
  });

  it.each<[string, ModelPropertiesInput, ReadonlyArray<string | number>]>([
    [
      "duplicate pricing types",
      withModalities({
        input: {
          pricing: [
            { type: "prompt", unit: "token", cost: 1 },
            { type: "prompt", unit: "token", cost: 2 },
          ],
        },
      }),
      ["input_modalities", 0, "pricing"],
    ],
    [
      "missing prompt pricing",
      withModalities({
        input: {
          pricing: [{ type: "cached_prompt", unit: "token", cost: 1 }],
        },
      }),
      ["input_modalities", 0, "pricing"],
    ],
    [
      "missing completion pricing",
      withModalities({
        output: {
          pricing: [{ type: "internal_reasoning", unit: "token", cost: 1 }],
        },
      }),
      ["output_modalities", 0, "pricing"],
    ],
    [
      "duplicate output pricing types",
      withModalities({
        output: {
          pricing: [
            { type: "completion", unit: "token", cost: 1 },
            { type: "completion", unit: "token", cost: 2 },
          ],
        },
      }),
      ["output_modalities", 0, "pricing"],
    ],
    [
      "max_prompt_length above max_context_length",
      withModalities({
        input: {
          supported_inputs: {
            max_context_length: { value: 512, unit: "token" },
            max_prompt_length: { value: 513, unit: "token" },
          },
        },
      }),
      ["input_modalities", 0],
    ],
    [
      "default_length above max_length",
      withModalities({
        output: { default_length: { value: 513, unit: "token" } },
      }),
      ["output_modalities", 0],
    ],
    [
      "a range parameter with min above max",
      withModalities({
        output: {
          supported_parameters: {
            temperature: { type: "range", min: 2, max: 1 },
          },
        },
      }),
      ["output_modalities", 0, "supported_parameters", "temperature"],
    ],
    [
      "an integer parameter with min above max",
      withModalities({
        output: {
          supported_parameters: { top_k: { type: "integer", min: 2, max: 1 } },
        },
      }),
      ["output_modalities", 0, "supported_parameters", "top_k"],
    ],
  ])("rejects %s", (_, properties, path) => {
    const result = ModelPropertiesInputSchema.safeParse(properties);

    expect(result.success).toBe(false);
    expect(result.error?.issues).toContainEqual(
      expect.objectContaining({ path }),
    );
  });
});

describe("ModelPropertiesSchema", () => {
  const canonical = ModelPropertiesInputSchema.parse(modelPropertiesInput());

  it("accepts optional type in external readers without adding it to legacy responses", () => {
    expect(
      ExternalModelSchema.shape.properties.parse(canonical),
    ).not.toHaveProperty("type");
    expect(
      ExternalModelSchema.shape.properties.parse({ ...canonical, type: "chat" })
        .type,
    ).toBe("chat");
  });

  it("keeps type out of stored properties and requires it in public responses", () => {
    expect(canonical).not.toHaveProperty("type");
    expect(ModelPropertiesSchema.parse(canonical)).toEqual(canonical);
    expect(
      ModelPropertiesInputSchema.safeParse({ ...canonical, type: "decision" })
        .success,
    ).toBe(false);
    expect(ModelSchema.shape.properties.safeParse(canonical).success).toBe(
      false,
    );
    expect(
      ModelSchema.shape.properties.parse({ ...canonical, type: "decision" })
        .type,
    ).toBe("decision");
    expect(
      ModelSchema.shape.properties.safeParse({ ...canonical, type: "unknown" })
        .success,
    ).toBe(false);
  });

  it("rejects input pricing without cached prompt pricing", () => {
    const result = ModelPropertiesSchema.safeParse({
      ...canonical,
      input_modalities: canonical.input_modalities.map((modality) => ({
        ...modality,
        pricing: [{ type: "prompt", unit: "token", cost: 0 }],
      })),
    });

    expect(result.success).toBe(false);
    expect(result.error?.issues).toContainEqual(
      expect.objectContaining({ path: ["input_modalities", 0, "pricing"] }),
    );
  });

  it("rejects supported reasoning without internal reasoning pricing", () => {
    const result = ModelPropertiesSchema.safeParse({
      ...canonical,
      output_modalities: canonical.output_modalities.map((modality) => ({
        ...modality,
        supported_parameters: { reasoning: { type: "boolean" } },
      })),
    });

    expect(result.success).toBe(false);
    expect(result.error?.issues).toContainEqual(
      expect.objectContaining({ path: ["output_modalities", 0] }),
    );
  });
});
