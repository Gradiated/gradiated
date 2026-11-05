import { modelDisplayName } from "@gradiated/contracts/model-catalog";
import type { CatalogModelInput } from "../service.js";

export const kev9bModelId = "jaredpalmer/kev-9b";
export const kev9bArtifactModelPath = "jaredpalmer/kev-9b";
export const kev9bBaseModelPath = "Qwen/Qwen3.5-9B-Base";

export const createKev9bModelConfiguration = () =>
  ({
    id: kev9bModelId,
    name: modelDisplayName(kev9bModelId),
    status: "unavailable",
    properties: {
      description:
        "Kev 9B answers typed questions about structured state, returning calibrated choices, probabilities and scores instead of generated text",
      released_at: "2026-09-20T22:42:14.000Z",
      hugging_face_id: kev9bArtifactModelPath,
      quantization: "bf16",
      tokenizer: "Qwen",
      input_modalities: [
        {
          type: "text",
          supported_inputs: {
            max_context_length: { value: 8_192, unit: "token" },
            max_prompt_length: { value: 8_192, unit: "token" },
          },
          pricing: [
            { type: "prompt", unit: "token", cost: 30 },
            { type: "cached_prompt", unit: "token", cost: 6 },
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
