export type ModelUseCase = "judge" | "training" | "comparison" | "serving";

type CatalogEntry = {
  id: string;
  supportedUses: readonly ModelUseCase[];
};

export const MODEL_CATALOG = [
  {
    id: "deepseek/deepseek-v4.1-flash",
    supportedUses: ["comparison", "serving"],
  },
  { id: "z-ai/glm-5.3-flash", supportedUses: ["comparison", "serving"] },
  { id: "jaredpalmer/kev-9b", supportedUses: ["serving"] },
  { id: "Qwen/Qwen3-0.6B", supportedUses: ["judge", "training", "comparison"] },
  { id: "openai/gpt-6-astra", supportedUses: ["judge", "comparison"] },
  { id: "openai/gpt-6-sol", supportedUses: ["judge", "comparison"] },
  { id: "openai/gpt-6-luna", supportedUses: ["judge", "comparison"] },
  { id: "openai/gpt-5.6-sol", supportedUses: ["judge", "comparison"] },
  { id: "openai/gpt-5", supportedUses: ["judge", "comparison"] },
  { id: "anthropic/claude-fable-5-1", supportedUses: ["judge", "comparison"] },
  { id: "anthropic/claude-opus-5-5", supportedUses: ["judge", "comparison"] },
  { id: "anthropic/claude-sonnet-5-5", supportedUses: ["judge", "comparison"] },
  { id: "anthropic/claude-opus-5", supportedUses: ["judge", "comparison"] },
  { id: "anthropic/claude-sonnet-5", supportedUses: ["judge", "comparison"] },
] as const satisfies readonly CatalogEntry[];

type ModelForUse<
  Use extends ModelUseCase,
  Entry = (typeof MODEL_CATALOG)[number],
> = Entry extends CatalogEntry
  ? Use extends Entry["supportedUses"][number]
    ? Entry
    : never
  : never;

export const modelsForUseCase = <Use extends ModelUseCase>(useCase: Use) =>
  MODEL_CATALOG.filter((model): model is ModelForUse<Use> =>
    (model.supportedUses as readonly ModelUseCase[]).includes(useCase),
  );

export const JUDGE_MODELS = modelsForUseCase("judge");
export const EVALUATION_JUDGES = JUDGE_MODELS.map((model) => model.id);
export type EvaluationJudgeId = (typeof EVALUATION_JUDGES)[number];
export const DEFAULT_EVALUATION_JUDGE =
  "openai/gpt-5.6-sol" satisfies EvaluationJudgeId;

export const TRAINING_BASE_MODELS = modelsForUseCase("training");

export const COMPARISON_MODELS = modelsForUseCase("comparison");

export const TRAINING_ONLY_MODELS = TRAINING_BASE_MODELS.filter(
  (model) =>
    !(model.supportedUses as readonly ModelUseCase[]).includes("serving"),
);

// Temporary user-authorized reference rates, not provider or GPU charges.
export const QWEN_PLACEHOLDER_PRICING = {
  model_id: "Qwen/Qwen3-0.6B",
  input_nano_usd_per_token: 50,
  output_nano_usd_per_token: 100,
} as const;
