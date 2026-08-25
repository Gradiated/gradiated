export const gemma4ModelId = "google/gemma-4-31b-it";
export const gemma4ArtifactModelPath = "google/gemma-4-31B-it";

export const createGemma4ModelConfiguration = () => ({
  id: gemma4ModelId,
  name: "Gemma 4 31B Instruct",
  status: "available" as const,
  properties: {
    description:
      "Google Gemma 4 31B Instruct on Gradiated's native single-H200 runtime.",
    released_at: "2026-08-22T14:09:29.651Z",
    hugging_face_id: gemma4ArtifactModelPath,
    quantization: "fp8" as const,
    tokenizer: "Gemma 4",
    input_modalities: [
      {
        type: "text" as const,
        supported_inputs: {
          max_context_length: { value: 8_192, unit: "token" as const },
        },
        pricing: [
          { type: "prompt" as const, unit: "token" as const, cost: 80 },
          {
            type: "cached_prompt" as const,
            unit: "token" as const,
            cost: 10,
          },
        ],
      },
    ],
    output_modalities: [
      {
        type: "text" as const,
        max_length: { value: 4_096, unit: "token" as const },
        default_length: { value: 128, unit: "token" as const },
        streaming: true,
        supported_parameters: {
          temperature: { type: "enum" as const, values: [0] },
        },
        pricing: [
          { type: "completion" as const, unit: "token" as const, cost: 350 },
        ],
      },
    ],
  },
});
