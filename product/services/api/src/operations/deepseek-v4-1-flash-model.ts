export const deepseekV41FlashModelId = "deepseek/deepseek-v4.1-flash";
export const deepseekV41FlashArtifactModelPath =
  "deepseek-ai/DeepSeek-V4.1-Flash";

// Most common provider prices on OpenRouter, observed 2026-09-14.
// Integer nano-USD per token: $0.30/M input, $0.006/M cache, $1.20/M output.
export const createDeepseekV41FlashModelConfiguration = () => ({
  id: deepseekV41FlashModelId,
  name: "DeepSeek V4.1 Flash",
  status: "available" as const,
  properties: {
    description:
      "DeepSeek V4.1 Flash with TP4 and DSpark speculative decoding.",
    released_at: "2026-09-10T00:00:00.000Z",
    hugging_face_id: deepseekV41FlashArtifactModelPath,
    quantization: "fp4" as const,
    tokenizer: "DeepSeek V4.1",
    input_modalities: [
      {
        type: "text" as const,
        supported_inputs: {
          max_context_length: { value: 1_048_576, unit: "token" as const },
        },
        pricing: [
          { type: "prompt" as const, unit: "token" as const, cost: 300 },
          { type: "cached_prompt" as const, unit: "token" as const, cost: 6 },
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
          reasoning_effort: { type: "unknown" as const },
          chat_template_kwargs: { type: "unknown" as const },
        },
        pricing: [
          { type: "completion" as const, unit: "token" as const, cost: 1_200 },
          {
            type: "internal_reasoning" as const,
            unit: "token" as const,
            cost: 1_200,
          },
        ],
      },
    ],
  },
});
