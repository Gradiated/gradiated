import { createDeepseekV41FlashModelConfiguration } from "./deepseek-v4-1-flash.js";
import { createGlm53FlashModelConfiguration } from "./glm-5-3-flash.js";
import { createKev9bModelConfiguration } from "./kev-9b.js";

export const catalogModels = [
  createDeepseekV41FlashModelConfiguration(),
  createGlm53FlashModelConfiguration(),
  createKev9bModelConfiguration(),
];
