import { modelDisplayName } from "@gradiated/contracts/model-catalog";
import type { CatalogModelInput } from "../service.js";

export const glm53ModelId = "z-ai/glm-5.3";
export const glm53ArtifactModelPath = "zai-org/GLM-5.3";

// Served from OpenRouter only; no GLM-5.3 deployment exists. Prices are the
// mode of Fireworks, Baseten and Modal on OpenRouter (checked 2026-11-06):
// all three charge $1.40 input and $4.40 output; Fireworks and Modal charge
// $0.26 cached input, Baseten $0.14.
export const createGlm53ModelConfiguration = () =>
  ({
    id: glm53ModelId,
    name: modelDisplayName(glm53ModelId),
    status: "available",
    // Checked 2026-11-06: OpenRouter's entry has this model's Hugging Face ID.
    openrouterModelId: "z-ai/glm-5.3",
    // Counts tokens while no deployment supplies a tokenizer.
    tokenizer: {
      path: glm53ArtifactModelPath,
      revision: "ba32f8c19c8738e2c57c71798c601d477a7bf844",
    },
    properties: {
      description:
        "GLM-5.3 is Z.AI's flagship reasoning, coding and tool-use model",
      released_at: "2026-08-25T00:00:00.000Z",
      hugging_face_id: glm53ArtifactModelPath,
      quantization: "fp8",
      tokenizer: "GLM",
      input_modalities: [
        {
          type: "text",
          supported_inputs: {
            max_context_length: { value: 1_048_576, unit: "token" },
          },
          pricing: [
            { type: "prompt", unit: "token", cost: 1_400 },
            { type: "cached_prompt", unit: "token", cost: 260 },
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
            seed: { type: "integer", min: 0, max: Number.MAX_SAFE_INTEGER },
            frequency_penalty: { type: "range", min: -2, max: 2 },
            presence_penalty: { type: "range", min: -2, max: 2 },
            stop: { type: "unknown" },
            tools: { type: "unknown" },
            tool_choice: { type: "unknown" },
            parallel_tool_calls: { type: "boolean" },
            reasoning: { type: "unknown" },
            reasoning_effort: { type: "enum", values: ["low", "high", "max"] },
            response_format: { type: "unknown" },
          },
          pricing: [
            { type: "completion", unit: "token", cost: 4_400 },
            { type: "internal_reasoning", unit: "token", cost: 4_400 },
          ],
        },
      ],
      // generation_config.json and the model card (reasoning_effort defaults to max).
      default_parameters: {
        temperature: 1,
        top_p: 0.95,
        frequency_penalty: 0,
        presence_penalty: 0,
      },
      reasoning: {
        supported_efforts: ["low", "high", "max"],
        default_effort: "max",
      },
    },
  }) satisfies CatalogModelInput;
