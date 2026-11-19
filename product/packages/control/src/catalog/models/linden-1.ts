import { modelDisplayName } from "@gradiated/contracts/model-catalog";
import type { CatalogModelInput } from "../service.js";

export const linden1ModelId = "gradiated/linden-1";
export const linden1ArtifactModelPath = "gradiated/linden-1";
export const linden1BaseModelPath = "google/gemma-4-31B-it";

export const createLinden1ModelConfiguration = () =>
  ({
    id: linden1ModelId,
    name: modelDisplayName(linden1ModelId),
    status: "available",
    openrouterModelId: null,
    properties: {
      description:
        "linden-1 answers typed questions about text and structured state, returning calibrated choices, probabilities and scores instead of generated text.",
      released_at: "2026-11-18T00:00:00.000Z",
      hugging_face_id: linden1ArtifactModelPath,
      quantization: "bf16",
      tokenizer: "Gemma",
      input_modalities: [
        {
          type: "text",
          supported_inputs: {
            max_context_length: { value: 32_768, unit: "token" },
            max_prompt_length: { value: 32_768, unit: "token" },
          },
          pricing: [
            { type: "prompt", unit: "token", cost: 20 },
            { type: "cached_prompt", unit: "token", cost: 20 },
          ],
        },
      ],
      output_modalities: [
        {
          type: "text",
          // Decisions generate no tokens; 1 is the smallest length the schema permits.
          max_length: { value: 1, unit: "token" },
          default_length: { value: 1, unit: "token" },
          streaming: false,
          supported_parameters: {},
          pricing: [{ type: "completion", unit: "token", cost: 0 }],
        },
      ],
      passthrough_parameters: {},
      deprecation_date: null,
    },
  }) satisfies CatalogModelInput;
