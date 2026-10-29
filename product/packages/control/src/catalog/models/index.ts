import { createDeepseekV41FlashModelConfiguration } from "./deepseek-v4-1-flash.js";
import {
  createDealignGlm53FlashModelConfiguration,
  createGlm53FlashModelConfiguration,
} from "./glm-5-3-flash.js";
import { createKev9bModelConfiguration } from "./kev-9b.js";

export const catalogModels = [
  createDeepseekV41FlashModelConfiguration(),
  createGlm53FlashModelConfiguration(),
  createDealignGlm53FlashModelConfiguration(),
  createKev9bModelConfiguration(),
];

export const legacyModels = [
  {
    ...createDealignGlm53FlashModelConfiguration(),
    id: "dealignai/glm-5.3-flash-uncensored-nvfp4",
    status: "retired" as const,
  },
];

export {
  createQwenSftModelConfiguration,
  trainingOnlyModels,
} from "./training.js";
