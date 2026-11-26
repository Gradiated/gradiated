import { agentsToolsPapers } from "./agents-tools";
import { distillationCompressionPapers } from "./distillation-compression";
import { embeddingsMultimodalPapers } from "./embeddings-multimodal";
import { peftMergingSafetyPapers } from "./peft-merging-safety";
import { preferenceAlignmentPapers } from "./preference-alignment";
import { rewardVerifiersPapers } from "./reward-verifiers";
import { rlReasoningPapers } from "./rl-reasoning";
import { routingSteeringTtsPapers } from "./routing-steering-tts";
import type { PaperGuide } from "./types";

export { paperCategories } from "./types";
export type {
  PaperCategory,
  PaperDatasetOption,
  PaperGuide,
  PaperMetricRow,
  PaperModelOption,
  PaperSmoothness,
  PaperWalkthroughStep,
} from "./types";

export const papers: PaperGuide[] = [
  ...rlReasoningPapers,
  ...preferenceAlignmentPapers,
  ...distillationCompressionPapers,
  ...rewardVerifiersPapers,
  ...agentsToolsPapers,
  ...routingSteeringTtsPapers,
  ...peftMergingSafetyPapers,
  ...embeddingsMultimodalPapers,
];

export const paperBySlug = (slug: string): PaperGuide | undefined =>
  papers.find((p) => p.slug === slug);
