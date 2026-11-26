export type PaperCategory =
  | "RL & Reasoning"
  | "Preference Alignment"
  | "Distillation & Compression"
  | "Reward Models & Verifiers"
  | "Agents & Tool Use"
  | "Routing, Inference & Steering"
  | "PEFT, Merging & Safety"
  | "Embeddings, Calibration & Multimodal";

export type PaperModelOption = {
  id: string;
  label: string;
  estTokens: string;
  duration: string;
  estCost: string;
};

export type PaperDatasetOption = {
  id: string;
  label: string;
  source: string;
  examples: string;
};

export type PaperMetricRow = {
  benchmark: string;
  paperReported: string;
  templateSetup: string;
};

export type PaperWalkthroughStep = {
  title: string;
  explanation: string;
  gradCall: string;
};

export type PaperSmoothness = {
  rating: "Effortless" | "Clean" | "Custom head / loop";
  verdict: string;
};

export type PaperGuide = {
  slug: string;
  shortTitle: string;
  title: string;
  authors: string;
  year: number;
  arxivId: string;
  arxivUrl: string;
  category: PaperCategory;
  oneLiner: string;
  story: string;
  insight: string;
  whyGrad: string;
  smoothness: PaperSmoothness;
  walkthrough: PaperWalkthroughStep[];
  gotchas: string[];
  linesOfCode: number;
  typicalBaselineLoc: string;
  mode: "Managed recipe" | "Custom loop";
  entrypoint: "train.py" | "recipe.yaml";
  models: PaperModelOption[];
  datasets: PaperDatasetOption[];
  primitives: Array<{ label: string; href: string }>;
  codeLabel: string;
  codeLanguage: "python" | "yaml";
  code: string;
  paperYaml: string;
  dryRunOutput: string;
  benchmarks: PaperMetricRow[];
  bibtex: string;
};

export const paperCategories: PaperCategory[] = [
  "RL & Reasoning",
  "Preference Alignment",
  "Distillation & Compression",
  "Reward Models & Verifiers",
  "Agents & Tool Use",
  "Routing, Inference & Steering",
  "PEFT, Merging & Safety",
  "Embeddings, Calibration & Multimodal",
];
