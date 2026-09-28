import type { CatalogModelInput } from "../service.js";

export const deepseekV41FlashModelId = "deepseek/deepseek-v4.1-flash";
export const deepseekV41FlashArtifactModelPath =
  "deepseek-ai/DeepSeek-V4.1-Flash";

// OpenRouter's most common provider prices on 2026-09-14, in nano-USD per token.
export const createDeepseekV41FlashModelConfiguration = () =>
  ({
    id: deepseekV41FlashModelId,
    name: "DeepSeek V4.1 Flash",
    status: "available",
    properties: {
      description:
        "DeepSeek V4.1 Flash with TP4 and DSpark speculative decoding.",
      released_at: "2026-09-10T00:00:00.000Z",
      hugging_face_id: deepseekV41FlashArtifactModelPath,
      quantization: "fp4",
      tokenizer: "DeepSeek V4.1",
      input_modalities: [
        {
          type: "text",
          supported_inputs: {
            max_context_length: { value: 1_048_576, unit: "token" },
          },
          pricing: [
            { type: "prompt", unit: "token", cost: 300 },
            { type: "cached_prompt", unit: "token", cost: 6 },
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
            reasoning_effort: { type: "unknown" },
            chat_template_kwargs: { type: "unknown" },
          },
          pricing: [
            { type: "completion", unit: "token", cost: 1_200 },
            {
              type: "internal_reasoning",
              unit: "token",
              cost: 1_200,
            },
          ],
        },
      ],
    },
  }) satisfies CatalogModelInput;
