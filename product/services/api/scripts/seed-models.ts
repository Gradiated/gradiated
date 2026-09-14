// Local catalog fixture. Sources and scope are recorded in product/README.md.
export const createDeepseekV41FlashSeedModel = () => ({
  id: "deepseek/deepseek-v4.1-flash",
  name: "DeepSeek V4.1 Flash",
  status: "available" as const,
  properties: {
    description:
      "DeepSeek V4.1 Flash local catalog fixture. Inference requires a matching deployment.",
    released_at: "2026-09-10T00:00:00.000Z",
    hugging_face_id: "deepseek-ai/DeepSeek-V4.1-Flash",
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
        max_length: { value: 1_048_576, unit: "token" as const },
        default_length: { value: 4_096, unit: "token" as const },
        streaming: true,
        supported_parameters: {
          temperature: { type: "range" as const, min: 0, max: 2 },
          top_p: { type: "range" as const, min: 0, max: 1 },
          tools: { type: "unknown" as const },
          tool_choice: { type: "unknown" as const },
          response_format: { type: "unknown" as const },
        },
        pricing: [
          { type: "completion" as const, unit: "token" as const, cost: 1200 },
          {
            type: "internal_reasoning" as const,
            unit: "token" as const,
            cost: 1200,
          },
        ],
      },
    ],
  },
});
