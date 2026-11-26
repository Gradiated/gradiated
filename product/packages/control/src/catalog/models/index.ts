import { createLinden1ModelConfiguration } from "./linden-1.js";
import { createDecider27bModelConfiguration } from "./decider-27b.js";
import { createDeepseekV41Flash1017ModelConfiguration } from "./deepseek-v4-1-flash-1017.js";
import { createDeepseekV41FlashModelConfiguration } from "./deepseek-v4-1-flash.js";
import {
  createGlm53FlashCyberModelConfiguration,
  createGlm53FlashModelConfiguration,
  dealignGlm53FlashUncensoredModelId,
} from "./glm-5-3-flash.js";
import { createGlm53ModelConfiguration } from "./glm-5-3.js";
import { createKev9bModelConfiguration } from "./kev-9b.js";
import {
  createKimiK31ProCyberModelConfiguration,
  createKimiK31ProModelConfiguration,
  yetalabsKimiK31ProAbliteratedModelId,
} from "./kimi-k31-pro.js";
import { createJeevesModelConfiguration } from "./posthog-jeeves.js";
import { createJevk5ModelConfiguration } from "./posthog-jevk5.js";

export const catalogModels = [
  createLinden1ModelConfiguration(),
  createDecider27bModelConfiguration(),
  createDeepseekV41Flash1017ModelConfiguration(),
  createGlm53FlashModelConfiguration(),
  createGlm53FlashCyberModelConfiguration(),
  createKev9bModelConfiguration(),
  createKimiK31ProModelConfiguration(),
  createKimiK31ProCyberModelConfiguration(),
  createGlm53ModelConfiguration(),
  // Organization-owned: never in MODEL_CATALOG, listed only to their owner.
  createJeevesModelConfiguration(),
  createJevk5ModelConfiguration(),
];

export const legacyModels = [
  {
    ...createGlm53FlashCyberModelConfiguration(),
    id: "dealignai/glm-5.3-flash-uncensored-nvfp4",
    aliases: [],
    status: "retired" as const,
  },
  {
    ...createGlm53FlashCyberModelConfiguration(),
    id: dealignGlm53FlashUncensoredModelId,
    aliases: [],
    status: "retired" as const,
  },
  {
    ...createKimiK31ProCyberModelConfiguration(),
    id: yetalabsKimiK31ProAbliteratedModelId,
    aliases: [],
    status: "retired" as const,
  },
  createDeepseekV41FlashModelConfiguration(),
];

export {
  createQwenSftModelConfiguration,
  trainingOnlyModels,
} from "./training.js";
