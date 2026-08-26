export const deepseekV4FlashModelId = "deepseek/deepseek-v4-flash-0731";
export const deepseekV4FlashArtifactModelPath =
  "deepseek-ai/DeepSeek-V4-Flash-0731";

export const createDeepseekV4FlashModelConfiguration = () => ({
  id: deepseekV4FlashModelId,
  name: "DeepSeek V4 Flash 0731",
  status: "available" as const,
  properties: {
    description:
      "DeepSeek V4 Flash 0731 on Gradiated's single-B300 Runpod runtime.",
    released_at: "2026-07-31T00:00:00.000Z",
    hugging_face_id: deepseekV4FlashArtifactModelPath,
    quantization: "fp4" as const,
    tokenizer: "DeepSeek V4",
    input_modalities: [
      {
        type: "text" as const,
        supported_inputs: {
          max_context_length: { value: 262_144, unit: "token" as const },
        },
        pricing: [
          { type: "prompt" as const, unit: "token" as const, cost: 60 },
          {
            type: "cached_prompt" as const,
            unit: "token" as const,
            cost: 12,
          },
        ],
      },
    ],
    output_modalities: [
      {
        type: "text" as const,
        max_length: { value: 32_768, unit: "token" as const },
        default_length: { value: 1_024, unit: "token" as const },
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
          tools: { type: "unknown" as const },
          tool_choice: { type: "unknown" as const },
          response_format: { type: "unknown" as const },
          stop: { type: "unknown" as const },
          reasoning: { type: "unknown" as const },
        },
        pricing: [
          { type: "completion" as const, unit: "token" as const, cost: 120 },
          {
            type: "internal_reasoning" as const,
            unit: "token" as const,
            cost: 120,
          },
        ],
      },
    ],
  },
});
