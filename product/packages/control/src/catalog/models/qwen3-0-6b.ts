import { TRAINING_RECIPE } from "@gradiated/contracts";
import type { CatalogModelInput } from "../service.js";

export const createQwenSftModelConfiguration = (): CatalogModelInput => ({
  id: TRAINING_RECIPE.model,
  name: "Qwen3 0.6B",
  status: "unavailable",
  properties: {
    description:
      "Training-only base for the Qwen SFT qualification recipe. Hosted inference and serving prices are not configured.",
    hugging_face_id: TRAINING_RECIPE.model,
    quantization: "bf16",
    tokenizer: "Qwen3",
    input_modalities: [
      {
        type: "text",
        supported_inputs: {
          max_context_length: {
            value: TRAINING_RECIPE.sequence_length,
            unit: "token",
          },
        },
        pricing: [{ type: "prompt", unit: "token", cost: 0 }],
      },
    ],
    output_modalities: [
      {
        type: "text",
        max_length: { value: TRAINING_RECIPE.sequence_length, unit: "token" },
        default_length: { value: 256, unit: "token" },
        streaming: false,
        supported_parameters: {},
        pricing: [{ type: "completion", unit: "token", cost: 0 }],
      },
    ],
  },
});
