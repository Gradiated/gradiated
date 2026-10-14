export type ModelUseCase = "judge" | "training" | "comparison" | "serving";

export type CatalogEntry = {
  id: string;
  displayName: string;
  icon: string | null;
  supportedUses: readonly ModelUseCase[];
  type?: "chat" | "decision";
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
    displayName: "DeepSeek V4.1 Flash",
    icon: "/model-providers/deepseek.svg",
    supportedUses: ["judge", "comparison", "serving"],
  },
  {
    id: "z-ai/glm-5.3-flash",
    displayName: "GLM-5.3 Flash",
    icon: "/model-providers/zai.svg",
    supportedUses: ["judge", "training", "comparison", "serving"],
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
  {
    id: "jaredpalmer/kev-9b",
    type: "decision",
    displayName: "Kev 9B",
    icon: null,
    supportedUses: ["serving"],
  },
  {
    id: "Qwen/Qwen3-0.6B",
    displayName: "Qwen3 0.6B",
    icon: "/model-providers/qwen.svg",
    supportedUses: ["judge", "training", "comparison"],
    training: { revision: "c1899de289a04d12100db370d81485cdf75e47ca" },
  },
  {
    id: "Qwen/Qwen3-1.7B",
    displayName: "Qwen3 1.7B",
    icon: "/model-providers/qwen.svg",
    supportedUses: ["training"],
    training: { revision: "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e" },
  },
  {
    id: "Qwen/Qwen3-4B",
    displayName: "Qwen3 4B",
    icon: "/model-providers/qwen.svg",
    supportedUses: ["training"],
    training: { revision: "1cfa9a7208912126459214e8b04321603b3df60c" },
  },
  {
    id: "Qwen/Qwen3-8B",
    displayName: "Qwen3 8B",
    icon: "/model-providers/qwen.svg",
    supportedUses: ["training"],
    training: { revision: "b968826d9c46dd6066d109eabc6255188de91218" },
  },
  {
    id: "Qwen/Qwen3-14B",
    displayName: "Qwen3 14B",
    icon: "/model-providers/qwen.svg",
    supportedUses: ["training"],
    training: { revision: "40c069824f4251a91eefaf281ebe4c544efd3e18" },
  },
  {
    id: "Qwen/Qwen3-32B",
    displayName: "Qwen3 32B",
    icon: "/model-providers/qwen.svg",
    supportedUses: ["training"],
    training: { revision: "9216db5781bf21249d130ec9da846c4624c16137" },
  },
  {
    id: "openai/gpt-6.1-sol",
    displayName: "GPT-6.1 Sol",
    icon: "/model-providers/openai.svg",
    supportedUses: ["judge", "comparison"],
  },
  {
    id: "openai/gpt-6.1-sol-pro",
    displayName: "GPT-6.1 Sol Pro",
    icon: "/model-providers/openai.svg",
    supportedUses: ["judge", "comparison"],
  },
  {
    id: "openai/gpt-6-astra",
    displayName: "GPT-6 Astra",
    icon: "/model-providers/openai.svg",
    supportedUses: ["judge", "comparison"],
  },
  {
    id: "openai/gpt-6-astra-pro",
    displayName: "GPT-6 Astra Pro",
    icon: "/model-providers/openai.svg",
    supportedUses: ["judge", "comparison"],
  },
  {
    id: "openai/gpt-6-sol",
    displayName: "GPT-6 Sol",
    icon: "/model-providers/openai.svg",
    supportedUses: ["judge", "comparison"],
  },
  {
    id: "openai/gpt-6-sol-pro",
    displayName: "GPT-6 Sol Pro",
    icon: "/model-providers/openai.svg",
    supportedUses: ["judge", "comparison"],
  },
  {
    id: "openai/gpt-6-luna",
    displayName: "GPT-6 Luna",
    icon: "/model-providers/openai.svg",
    supportedUses: ["judge", "comparison"],
  },
  {
    id: "openai/gpt-6-luna-pro",
    displayName: "GPT-6 Luna Pro",
    icon: "/model-providers/openai.svg",
    supportedUses: ["judge", "comparison"],
  },
  {
    id: "openai/gpt-5.6-sol",
    displayName: "GPT-5.6 Sol",
    icon: "/model-providers/openai.svg",
    supportedUses: ["judge", "comparison"],
  },
  {
    id: "openai/gpt-5",
    displayName: "GPT-5",
    icon: "/model-providers/openai.svg",
    supportedUses: ["judge", "comparison"],
  },
  {
    id: "anthropic/claude-fable-5-1",
    displayName: "Claude Fable 5.1",
    icon: "/model-providers/anthropic.svg",
    supportedUses: ["judge", "comparison"],
  },
  {
    id: "anthropic/claude-opus-5-5",
    displayName: "Claude Opus 5.5",
    icon: "/model-providers/anthropic.svg",
    supportedUses: ["judge", "comparison"],
  },
  {
    id: "anthropic/claude-sonnet-5-5",
    displayName: "Claude Sonnet 5.5",
    icon: "/model-providers/anthropic.svg",
    supportedUses: ["judge", "comparison"],
  },
  {
    id: "anthropic/claude-haiku-5-5",
    displayName: "Claude Haiku 5.5",
    icon: "/model-providers/anthropic.svg",
    supportedUses: ["judge", "comparison"],
  },
  {
    id: "anthropic/claude-opus-5",
    displayName: "Claude Opus 5",
    icon: "/model-providers/anthropic.svg",
    supportedUses: ["judge", "comparison"],
  },
  {
    id: "anthropic/claude-sonnet-5",
    displayName: "Claude Sonnet 5",
    icon: "/model-providers/anthropic.svg",
    supportedUses: ["judge", "comparison"],
  },
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

export const JUDGE_MODELS = modelsForUseCase("comparison");
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

export const catalogModel = (id: string) =>
  MODEL_CATALOG.find((model) => model.id === id);

export const modelType = (id: string): "chat" | "decision" => {
  const model: CatalogEntry | undefined = catalogModel(id);

  return model?.type ?? "chat";
};

export const modelDisplayName = (id: string | null | undefined) =>
  id ? (catalogModel(id)?.displayName ?? id) : "—";

export const isExternalModelId = (id: string) =>
  /^(openai|anthropic)\/[a-zA-Z0-9._-]+$/.test(id);

export const isEvaluationModelId = (id: string) =>
  isExternalModelId(id) || COMPARISON_MODELS.some((model) => model.id === id);

export const modelProviderIcon = (id: string) =>
  catalogModel(id)?.icon ??
  (id.startsWith("openai/")
    ? "/model-providers/openai.svg"
    : id.startsWith("anthropic/")
      ? "/model-providers/anthropic.svg"
      : null);
