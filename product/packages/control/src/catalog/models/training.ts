import {
  modelDisplayName,
  TRAINING_ONLY_MODELS,
} from "@gradiated/contracts/model-catalog";
import { TRAINING_RECIPE, trainingRecipeForModel } from "@gradiated/contracts";
import type { CatalogModelInput } from "../service.js";

export const createTrainingModelConfiguration = (
  modelId: string,
): CatalogModelInput => {
  const recipe = trainingRecipeForModel(modelId);
  if (!recipe) throw new Error("Training recipe is unavailable.");

  return {
    id: recipe.model,
    name: modelDisplayName(modelId),
    status: "unavailable",
    properties: {
      description:
        "Training base. Hosted inference and serving prices are not configured.",
      hugging_face_id: recipe.model,
      quantization: "bf16",
      tokenizer: "Qwen3",
      input_modalities: [
        {
          type: "text",
          supported_inputs: {
            max_context_length: {
              value: recipe.sequence_length,
              unit: "token",
            },
          },
          pricing: [{ type: "prompt", unit: "token", cost: 0 }],
        },
      ],
      output_modalities: [
        {
          type: "text",
          max_length: { value: recipe.sequence_length, unit: "token" },
          default_length: { value: 256, unit: "token" },
          streaming: false,
          supported_parameters: {},
          pricing: [{ type: "completion", unit: "token", cost: 0 }],
        },
      ],
    },
  };
};

export const createQwenSftModelConfiguration = () =>
  createTrainingModelConfiguration(TRAINING_RECIPE.model);

export const trainingOnlyModels = () =>
  TRAINING_ONLY_MODELS.map((model) =>
    createTrainingModelConfiguration(model.id),
  );
