import type { CatalogModelInput } from "../service.js";

export const jevk5ModelId = "posthog/jevk5";
export const jevk5ArtifactModelPath = "alibiserikbay/JevK5";
export const jevk5BaseModelPath = "Qwen/Qwen3.5-4B";

export const createJevk5ModelConfiguration = () =>
  ({
    id: jevk5ModelId,
    name: "JevK5",
    status: "available",
    type: "decision",
    owner: { organizationSlug: "posthog" },
    openrouterModelId: null,
    properties: {
      description:
        "JevK5 v0.3 is PostHog's decision model, Qwen3.5-4B reading each option as an answer letter. It answers typed questions with calibrated choices, probabilities and scores instead of generated text.",
      // The pinned revision's commit time.
      released_at: "2026-09-25T06:07:03.000Z",
      hugging_face_id: jevk5ArtifactModelPath,
      quantization: "bf16",
      tokenizer: "Qwen",
      input_modalities: [
        {
          type: "text",
          // The runtime refuses a longer prompt rather than truncating it.
          supported_inputs: {
            max_context_length: { value: 16_384, unit: "token" },
            max_prompt_length: { value: 16_384, unit: "token" },
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
