export type ModelUseCase = "judge";

type CatalogEntry = {
  id: string;
  supportedUses: readonly ModelUseCase[];
};

export const MODEL_CATALOG = [
  { id: "Qwen/Qwen3-0.6B", supportedUses: ["judge"] },
  { id: "openai/gpt-6-astra", supportedUses: ["judge"] },
  { id: "openai/gpt-6-sol", supportedUses: ["judge"] },
  { id: "openai/gpt-6-luna", supportedUses: ["judge"] },
  { id: "openai/gpt-5.6-sol", supportedUses: ["judge"] },
  { id: "openai/gpt-5", supportedUses: ["judge"] },
  { id: "anthropic/claude-fable-5-1", supportedUses: ["judge"] },
  { id: "anthropic/claude-opus-5-5", supportedUses: ["judge"] },
  { id: "anthropic/claude-sonnet-5-5", supportedUses: ["judge"] },
  { id: "anthropic/claude-opus-5", supportedUses: ["judge"] },
  { id: "anthropic/claude-sonnet-5", supportedUses: ["judge"] },
] as const satisfies readonly CatalogEntry[];

export const modelsForUseCase = (useCase: ModelUseCase) =>
  MODEL_CATALOG.filter((model) =>
    (model.supportedUses as readonly ModelUseCase[]).includes(useCase),
  );

export const JUDGE_MODELS = modelsForUseCase("judge");
export const EVALUATION_JUDGES = JUDGE_MODELS.map((model) => model.id);
export type EvaluationJudgeId = (typeof EVALUATION_JUDGES)[number];
export const DEFAULT_EVALUATION_JUDGE =
  "openai/gpt-5.6-sol" satisfies EvaluationJudgeId;
