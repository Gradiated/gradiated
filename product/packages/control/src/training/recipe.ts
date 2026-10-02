import { TrainingAdmissionError, type TrainingInput } from "./types.js";
import { trainingRecipeForModel, TRAINING_RECIPE } from "@gradiated/contracts";

export const QWEN_SFT_MODEL = TRAINING_RECIPE.model;
export const validateSftInput = (input: TrainingInput) => {
  if (!trainingRecipeForModel(input.baseModelId))
    throw new TrainingAdmissionError(
      "training_not_configured",
      `Training is not configured for ${input.baseModelId}.`,
    );
  return input;
};
