import { createDeepseekV41Flash1017ModelConfiguration } from "./deepseek-v4-1-flash-1017.js";
import { createDeepseekV41FlashModelConfiguration } from "./deepseek-v4-1-flash.js";
import {
  createDealignGlm53FlashModelConfiguration,
  createGlm53FlashModelConfiguration,
} from "./glm-5-3-flash.js";
import { createGlm53ModelConfiguration } from "./glm-5-3.js";
import { createKev9bModelConfiguration } from "./kev-9b.js";
import { createKimiK31ProModelConfiguration } from "./kimi-k31-pro.js";

export const catalogModels = [
  createDeepseekV41Flash1017ModelConfiguration(),
  createDeepseekV41FlashModelConfiguration(),
  createGlm53FlashModelConfiguration(),
  createDealignGlm53FlashModelConfiguration(),
  createKev9bModelConfiguration(),
  createKimiK31ProModelConfiguration(),
  createGlm53ModelConfiguration(),
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
