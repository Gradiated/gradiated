import { modelDisplayName } from "@gradiated/contracts/model-catalog";
import type { CatalogModelInput } from "../service.js";

export const decider27bModelId = "perplexity-ai/pplx-decider-v1.2";
export const decider27bArtifactModelPath = "perplexity-ai/pplx-decider-v1.2";
export const decider27bBaseModelPath = "Qwen/Qwen3.8-27B";

export const createDecider27bModelConfiguration = () =>
  ({
    id: decider27bModelId,
    name: modelDisplayName(decider27bModelId),
    status: "retired",
    type: "decision",
    openrouterModelId: null,
    properties: {
      description:
        "Decider v1.2 27B answers typed questions about text and structured state, returning choices, probabilities and scores instead of generated text.",
      released_at: "2026-10-16T00:00:00.000Z",
      hugging_face_id: "perplexity-ai/pplx-decider-v1.2",
      quantization: "int4",
      tokenizer: "Qwen",
      input_modalities: [
        {
          type: "text",
          supported_inputs: {
            max_context_length: { value: 8_192, unit: "token" },
            max_prompt_length: { value: 8_192, unit: "token" },
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
