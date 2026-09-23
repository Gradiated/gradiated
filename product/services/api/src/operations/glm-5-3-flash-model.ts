import type { CatalogModelInput } from "./catalog-operation.js";

export const glm53FlashModelId = "z-ai/glm-5.3-flash";
export const glm53FlashArtifactModelPath = "zai-org/GLM-5.3-Flash";

export const createGlm53FlashModelConfiguration = () =>
  ({
    id: glm53FlashModelId,
    name: "GLM-5.3 Flash",
    status: "available",
    properties: {
      description:
        "GLM-5.3 Flash is a fast reasoning and tool-use model from Z.AI",
      released_at: "2026-08-27T00:00:00.000Z",
      hugging_face_id: glm53FlashArtifactModelPath,
      quantization: "fp8",
      tokenizer: "GLM",
      input_modalities: [
        {
          type: "text",
          supported_inputs: {
            max_context_length: { value: 1_048_576, unit: "token" },
          },
          pricing: [
            { type: "prompt", unit: "token", cost: 75 },
            {
              type: "cached_prompt",
              unit: "token",
              cost: 15,
            },
          ],
        },
      ],
      output_modalities: [
        {
          type: "text",
          max_length: { value: 131_072, unit: "token" },
          default_length: { value: 4_096, unit: "token" },
          streaming: true,
          supported_parameters: {
            temperature: { type: "range", min: 0, max: 2 },
            top_p: { type: "range", min: 0, max: 1 },
            seed: {
              type: "integer",
              min: 0,
              max: Number.MAX_SAFE_INTEGER,
            },
            frequency_penalty: { type: "range", min: -2, max: 2 },
            presence_penalty: { type: "range", min: -2, max: 2 },
            stop: { type: "unknown" },
            tools: { type: "unknown" },
            tool_choice: { type: "unknown" },
            parallel_tool_calls: { type: "boolean" },
            reasoning: { type: "unknown" },
            response_format: { type: "unknown" },
          },
          pricing: [
            { type: "completion", unit: "token", cost: 250 },
            {
              type: "internal_reasoning",
              unit: "token",
              cost: 250,
            },
          ],
        },
      ],
    },
  }) satisfies CatalogModelInput;
