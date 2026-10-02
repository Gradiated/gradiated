import recipe from "./training-recipe.json" with { type: "json" };

import { TRAINING_BASE_MODELS, type CatalogEntry } from "./model-catalog.js";

export const TRAINING_RECIPE = recipe;

export const trainingRecipeForModel = (modelId: string) => {
  const model = TRAINING_BASE_MODELS.find((model) => model.id === modelId);
  if (!model) return null;
  const training: NonNullable<CatalogEntry["training"]> = model.training;
  return {
    ...recipe,
    ...training,
    id: `${model.id.toLowerCase().replaceAll("/", "-")}-sft-v1`,
    model: training.model ?? model.id,
    revision: training.revision,
  };
};
