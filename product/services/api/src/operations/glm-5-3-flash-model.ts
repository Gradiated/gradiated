export const glm53FlashModelId = "z-ai/glm-5.3-flash";
export const glm53FlashArtifactModelPath = "zai-org/GLM-5.3-Flash";

export const createGlm53FlashModelConfiguration = () => ({
  id: glm53FlashModelId,
  name: "GLM-5.3 Flash",
  status: "available" as const,
  properties: {
    description: "GLM-5.3 Flash FP8 on Gradiated B300 runtimes.",
    released_at: "2026-08-27T00:00:00.000Z",
    hugging_face_id: glm53FlashArtifactModelPath,
    quantization: "fp8" as const,
    tokenizer: "GLM",
    input_modalities: [
      {
        type: "text" as const,
        supported_inputs: {
          max_context_length: { value: 1_048_576, unit: "token" as const },
        },
        pricing: [
          { type: "prompt" as const, unit: "token" as const, cost: 75 },
          {
            type: "cached_prompt" as const,
            unit: "token" as const,
            cost: 15,
          },
        ],
      },
    ],
    output_modalities: [
      {
        type: "text" as const,
        max_length: { value: 131_072, unit: "token" as const },
        default_length: { value: 4_096, unit: "token" as const },
        streaming: true,
        supported_parameters: {
          temperature: { type: "range" as const, min: 0, max: 2 },
          top_p: { type: "range" as const, min: 0, max: 1 },
          seed: {
            type: "integer" as const,
            min: 0,
            max: Number.MAX_SAFE_INTEGER,
          },
          frequency_penalty: { type: "range" as const, min: -2, max: 2 },
          presence_penalty: { type: "range" as const, min: -2, max: 2 },
          stop: { type: "unknown" as const },
          tools: { type: "unknown" as const },
          tool_choice: { type: "unknown" as const },
          parallel_tool_calls: { type: "boolean" as const },
          reasoning: { type: "unknown" as const },
          response_format: { type: "unknown" as const },
        },
        pricing: [
          { type: "completion" as const, unit: "token" as const, cost: 250 },
          {
            type: "internal_reasoning" as const,
            unit: "token" as const,
            cost: 250,
          },
        ],
      },
    ],
  },
});
