import { modelDisplayName } from "@gradiated/contracts/model-catalog";
import type { CatalogModelInput } from "../service.js";

export const glm53FlashModelId = "z-ai/glm-5.3-flash";
export const glm53FlashArtifactModelPath = "zai-org/GLM-5.3-Flash";
export const glm53FlashCyberModelId = "glm-5.3-flash-cyber";
export const dealignGlm53FlashUncensoredModelId =
  "dealignai/glm-5.3-flash-uncensored";

export const createGlm53FlashModelConfiguration = () =>
  ({
    id: glm53FlashModelId,
    name: modelDisplayName(glm53FlashModelId),
    status: "available",
    type: "chat",
    // Checked 2026-11-05: OpenRouter's entry has this model's Hugging Face ID.
    openrouterModelId: "z-ai/glm-5.3-flash",
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
            { type: "prompt", unit: "token", cost: 150 },
            {
              type: "cached_prompt",
              unit: "token",
              cost: 30,
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
            { type: "completion", unit: "token", cost: 500 },
            {
              type: "internal_reasoning",
              unit: "token",
              cost: 500,
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

export const createGlm53FlashCyberModelConfiguration = () => {
  const base = createGlm53FlashModelConfiguration();

  return {
    ...base,
    id: glm53FlashCyberModelId,
    aliases: [
      dealignGlm53FlashUncensoredModelId,
      "dealignai/glm-5.3-flash-cyber",
      "glm-5.3-flash-uncensored",
    ],
    name: modelDisplayName(glm53FlashCyberModelId),
    status: "available",
    type: "chat",
    // OpenRouter does not serve Dealign's weights; standard GLM is a different model.
    openrouterModelId: null,
    properties: {
      ...base.properties,
      description:
        "Dealign's GLM 5.3 Flash Cyber (NVFP4) with retained reasoning and tool use",
      released_at: "2026-08-29T00:00:00.000Z",
      hugging_face_id: "dealignai/GLM-5.3-Flash-UNCENSORED-NVFP4",
      quantization: "nvfp4",
      input_modalities: base.properties.input_modalities.map((modality) => ({
        ...modality,
        pricing: [
          { type: "prompt", unit: "token", cost: 150 },
          { type: "cached_prompt", unit: "token", cost: 15 },
        ],
      })),
      output_modalities: base.properties.output_modalities.map((modality) => ({
        ...modality,
        pricing: [
          { type: "completion", unit: "token", cost: 450 },
          { type: "internal_reasoning", unit: "token", cost: 450 },
        ],
      })),
    },
  } satisfies CatalogModelInput;
};
