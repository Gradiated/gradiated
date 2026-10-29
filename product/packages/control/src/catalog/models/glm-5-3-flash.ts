import { modelDisplayName } from "@gradiated/contracts/model-catalog";
import type { CatalogModelInput } from "../service.js";

export const glm53FlashModelId = "z-ai/glm-5.3-flash";
export const glm53FlashArtifactModelPath = "zai-org/GLM-5.3-Flash";

export const createGlm53FlashModelConfiguration = () =>
  ({
    id: glm53FlashModelId,
    name: modelDisplayName(glm53FlashModelId),
    status: "available",
    properties: {
      description:
        "GLM-5.3 Flash is a fast reasoning and tool-use model from Z.AI",
      released_at: "2026-08-27T00:00:00.000Z",
      hugging_face_id: glm53FlashArtifactModelPath,
      quantization: "fp8",
      tokenizer: "GLM",
      input_modalities: [
        {
          type: "text",
          supported_inputs: {
            max_context_length: { value: 1_048_576, unit: "token" },
          },
          pricing: [
            { type: "prompt", unit: "token", cost: 75 },
            {
              type: "cached_prompt",
              unit: "token",
              cost: 15,
            },
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
            reasoning: { type: "unknown" },
            reasoning_effort: { type: "enum", values: ["low", "high", "max"] },
            response_format: { type: "unknown" },
          },
          pricing: [
            { type: "completion", unit: "token", cost: 250 },
            {
              type: "internal_reasoning",
              unit: "token",
              cost: 250,
            },
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

export const createDealignGlm53FlashModelConfiguration = () => {
  const base = createGlm53FlashModelConfiguration();
  const id = "dealignai/glm-5.3-flash-uncensored-nvfp4";

  return {
    ...base,
    id,
    name: modelDisplayName(id),
    status: "available",
    properties: {
      ...base.properties,
      description:
        "Dealign's weight-modified GLM-5.3 Flash with NVFP4 routed experts and retained reasoning and tool use",
      released_at: "2026-08-29T00:00:00.000Z",
      hugging_face_id: "dealignai/GLM-5.3-Flash-UNCENSORED-NVFP4",
      quantization: "nvfp4",
    },
  } satisfies CatalogModelInput;
};
