import { modelDisplayName } from "@gradiated/contracts/model-catalog";
import type { CatalogModelInput } from "../service.js";

export const deepseekV41Flash1017ModelId = "deepseek/deepseek-v4.1-flash-1017";
export const deepseekV41Flash1017ArtifactModelPath =
  "deepseek-ai/DeepSeek-V4.1-Flash-1017";

// Prices match OpenRouter's entry on 2026-11-10 ($0.006 input, $0.005 cached and
// $0.50 output per 1M tokens), so its fallback, capped at our price, still serves.
export const createDeepseekV41Flash1017ModelConfiguration = () =>
  ({
    id: deepseekV41Flash1017ModelId,
    name: modelDisplayName(deepseekV41Flash1017ModelId),
    status: "available",
    // Checked 2026-11-10: OpenRouter's entry has this model's Hugging Face ID.
    openrouterModelId: "deepseek/deepseek-v4.1-flash-1017",
    properties: {
      description:
        "DeepSeek V4.1 Flash 1017 with TP4 and DSpark speculative decoding.",
      released_at: "2026-10-17T00:00:00.000Z",
      hugging_face_id: deepseekV41Flash1017ArtifactModelPath,
      // The checkpoint's native weights: FP8 attention and shared experts, MXFP4
      // routed experts (FP4 with UE8M0 scales per 32 values). The field names one
      // format, so it records the experts, which hold most of the weights.
      quantization: "mxfp4",
      tokenizer: "DeepSeek V4.1",
      input_modalities: [
        {
          type: "text",
          supported_inputs: {
            max_context_length: { value: 1_048_576, unit: "token" },
          },
          pricing: [
            { type: "prompt", unit: "token", cost: 6 },
            { type: "cached_prompt", unit: "token", cost: 5 },
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
            { type: "completion", unit: "token", cost: 500 },
            {
              type: "internal_reasoning",
              unit: "token",
              cost: 500,
            },
          ],
        },
      ],
      // No generation_config.json, so the runtime's sampling defaults apply. The
      // gateway renders an omitted effort as high; integers 1-100 are also accepted.
      default_parameters: {
        temperature: 1,
        top_p: 1,
        frequency_penalty: 0,
        presence_penalty: 0,
      },
      reasoning: {
        supported_efforts: ["none", "low", "high", "xhigh", "max"],
        default_effort: "high",
      },
    },
  }) satisfies CatalogModelInput;
