export type ModelUseCase = "judge" | "training" | "comparison" | "serving";

export type CatalogEntry = {
  id: string;
  supportedUses: readonly ModelUseCase[];
  training?: {
    revision: string;
    model?: string;
    model_task?: string;
    gpu_count?: number;
    sequence_length?: number;
    attention?: string;
    target_modules?: readonly string[];
    gradient_checkpointing?: boolean;
  };
};

export const MODEL_CATALOG = [
  {
    id: "deepseek/deepseek-v4.1-flash",
    supportedUses: ["comparison", "serving"],
  },
  {
    id: "z-ai/glm-5.3-flash",
    supportedUses: ["training", "comparison", "serving"],
    training: {
      model: "zai-org/GLM-5.3-Flash-BF16",
      revision: "a5b45eb41df6402735dedc900be14a42e8d5e538",
      model_task: "image_text_to_text",
      gpu_count: 4,
      sequence_length: 512,
      attention: "eager",
      gradient_checkpointing: true,
      target_modules: [
        "q_proj",
        "k_proj",
        "v_proj",
        "o_proj",
        "q_a_proj",
        "q_b_proj",
        "kv_a_proj_with_mqa",
        "kv_b_proj",
      ],
    },
  },
  { id: "jaredpalmer/kev-9b", supportedUses: ["serving"] },
  {
    id: "Qwen/Qwen3-0.6B",
    supportedUses: ["judge", "training", "comparison"],
    training: { revision: "c1899de289a04d12100db370d81485cdf75e47ca" },
  },
  {
    id: "Qwen/Qwen3-1.7B",
    supportedUses: ["training"],
    training: { revision: "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e" },
  },
  {
    id: "Qwen/Qwen3-4B",
    supportedUses: ["training"],
    training: { revision: "1cfa9a7208912126459214e8b04321603b3df60c" },
  },
  {
    id: "Qwen/Qwen3-8B",
    supportedUses: ["training"],
    training: { revision: "b968826d9c46dd6066d109eabc6255188de91218" },
  },
  {
    id: "Qwen/Qwen3-14B",
    supportedUses: ["training"],
    training: { revision: "40c069824f4251a91eefaf281ebe4c544efd3e18" },
  },
  {
    id: "Qwen/Qwen3-32B",
    supportedUses: ["training"],
    training: { revision: "9216db5781bf21249d130ec9da846c4624c16137" },
  },
  { id: "openai/gpt-6.1-sol", supportedUses: ["judge", "comparison"] },
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
  "openai/gpt-6.1-sol" satisfies EvaluationJudgeId;

export const DEFAULT_TRAINING_BASE = "z-ai/glm-5.3-flash";

export const DEFAULT_COMPARISON_MODEL = DEFAULT_EVALUATION_JUDGE;

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
