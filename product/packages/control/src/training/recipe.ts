import { TrainingAdmissionError, type TrainingInput } from "./types.js";

import { TRAINING_RECIPE } from "@gradiated/contracts";

export const QWEN_SFT_MODEL = TRAINING_RECIPE.model;
export const validateSftInput = (input: TrainingInput) => {
  if (
    [input.baseModelId, input.comparisonModelId, input.judgeModelId].some(
      (model) => model !== QWEN_SFT_MODEL,
    )
  )
    throw new TrainingAdmissionError(
      "training_not_configured",
      `The initial SFT recipe requires ${QWEN_SFT_MODEL} as the base, comparison and workspace judge model.`,
    );
  return input;
};
