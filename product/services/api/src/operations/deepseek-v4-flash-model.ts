import type { CatalogModelInput } from "./catalog-operation.js";

export const deepseekV4FlashModelId = "deepseek/deepseek-v4-flash-0731";
export const deepseekV4FlashArtifactModelPath =
  "deepseek-ai/DeepSeek-V4-Flash-0731";

export const createDeepseekV4FlashModelConfiguration = () =>
  ({
    id: deepseekV4FlashModelId,
    name: "DeepSeek V4 Flash 0731",
    status: "available",
    properties: {
      description:
        "DeepSeek V4 Flash 0731 on Gradiated's single-B300 Runpod runtime.",
      released_at: "2026-07-31T00:00:00.000Z",
      hugging_face_id: deepseekV4FlashArtifactModelPath,
      quantization: "fp4",
      tokenizer: "DeepSeek V4",
      input_modalities: [
        {
          type: "text",
          supported_inputs: {
            max_context_length: { value: 262_144, unit: "token" },
          },
          pricing: [
            { type: "prompt", unit: "token", cost: 60 },
            {
              type: "cached_prompt",
              unit: "token",
              cost: 12,
            },
          ],
        },
      ],
      output_modalities: [
        {
          type: "text",
          max_length: { value: 32_768, unit: "token" },
          default_length: { value: 1_024, unit: "token" },
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
          },
          pricing: [
            { type: "completion", unit: "token", cost: 120 },
            {
              type: "internal_reasoning",
              unit: "token",
              cost: 120,
            },
          ],
        },
      ],
    },
  }) satisfies CatalogModelInput;
