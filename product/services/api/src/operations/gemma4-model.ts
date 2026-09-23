import type { CatalogModelInput } from "./catalog-operation.js";

export const gemma4ModelId = "google/gemma-4-31b-it";
export const gemma4ArtifactModelPath = "google/gemma-4-31B-it";

export const createGemma4ModelConfiguration = () =>
  ({
    id: gemma4ModelId,
    name: "Gemma 4 31B Instruct",
    status: "available",
    properties: {
      description:
        "Google Gemma 4 31B Instruct on Gradiated's native single-H200 runtime.",
      released_at: "2026-08-22T14:09:29.651Z",
      hugging_face_id: gemma4ArtifactModelPath,
      quantization: "fp8",
      tokenizer: "Gemma 4",
      input_modalities: [
        {
          type: "text",
          supported_inputs: {
            max_context_length: { value: 8_192, unit: "token" },
          },
          pricing: [
            { type: "prompt", unit: "token", cost: 80 },
            {
              type: "cached_prompt",
              unit: "token",
              cost: 10,
            },
          ],
        },
      ],
      output_modalities: [
        {
          type: "text",
          max_length: { value: 4_096, unit: "token" },
          default_length: { value: 128, unit: "token" },
          streaming: true,
          supported_parameters: {
            temperature: { type: "enum", values: [0] },
          },
          pricing: [{ type: "completion", unit: "token", cost: 350 }],
        },
      ],
    },
  }) satisfies CatalogModelInput;
