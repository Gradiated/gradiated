import { createLinden1ModelConfiguration } from "./linden-1.js";
import { createDecider27bModelConfiguration } from "./decider-27b.js";
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
  createLinden1ModelConfiguration(),
  createDecider27bModelConfiguration(),
  createDeepseekV41Flash1017ModelConfiguration(),
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
  createDeepseekV41FlashModelConfiguration(),
];

export {
  createQwenSftModelConfiguration,
  trainingOnlyModels,
} from "./training.js";
