export const kev9bModelId = "jaredpalmer/kev-9b";
export const kev9bArtifactModelPath = "jaredpalmer/kev-9b";
export const kev9bBaseModelPath = "Qwen/Qwen3.5-9B-Base";

/**
 * A decision model rather than a chat model: it answers typed questions about
 * structured state and generates nothing, so it is billed on input alone and
 * cannot stream. The output modality still has to be declared because the catalog
 * schema requires one, so it declares the smallest possible length at no cost.
 */
export const createKev9bModelConfiguration = () => ({
  id: kev9bModelId,
  name: "Kev 9B",
  status: "available" as const,
  properties: {
    description:
      "Kev 9B answers typed questions about structured state, returning calibrated choices, probabilities and scores instead of generated text",
    released_at: "2026-09-20T22:42:14.000Z",
    hugging_face_id: kev9bArtifactModelPath,
    quantization: "bf16" as const,
    tokenizer: "Qwen",
    input_modalities: [
      {
        type: "text" as const,
        supported_inputs: {
          // The runtime bounds a packed or padded request at this many tokens.
          max_context_length: { value: 8_192, unit: "token" as const },
          max_prompt_length: { value: 8_192, unit: "token" as const },
        },
        pricing: [
          { type: "prompt" as const, unit: "token" as const, cost: 30 },
          { type: "cached_prompt" as const, unit: "token" as const, cost: 6 },
        ],
      },
    ],
    output_modalities: [
      {
        type: "text" as const,
        // Decisions settle zero generated tokens, and the gateway rejects a
        // decision response that reports otherwise. One is the smallest length
        // the schema permits, priced at nothing so it can never be charged.
        max_length: { value: 1, unit: "token" as const },
        default_length: { value: 1, unit: "token" as const },
        streaming: false,
        supported_parameters: {},
        pricing: [
          { type: "completion" as const, unit: "token" as const, cost: 0 },
        ],
      },
    ],
    passthrough_parameters: {},
    deprecation_date: null,
  },
});
