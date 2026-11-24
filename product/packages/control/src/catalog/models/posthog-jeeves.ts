import type { CatalogModelInput } from "../service.js";

export const jeevesModelId = "posthog/jeeves";
export const jeevesArtifactModelPath = "PostHog/jeeves-fp8";
export const jeevesBaseModelPath = "Qwen/Qwen3.5-9B";

export const createJeevesModelConfiguration = () =>
  ({
    id: jeevesModelId,
    name: "Jeeves",
    status: "available",
    type: "decision",
    owner: { organizationSlug: "posthog" },
    openrouterModelId: null,
    properties: {
      description:
        "Jeeves v2 is PostHog's decision model, Qwen3.5-9B with a pointer head that scores each option. It answers typed questions with calibrated choices, probabilities and scores instead of generated text.",
      // The pinned FP8 revision's commit time.
      released_at: "2026-10-20T10:40:16.000Z",
      hugging_face_id: jeevesArtifactModelPath,
      quantization: "fp8",
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
