/* Facts the training widgets compute with. Each block names the grad source it
   mirrors, so a change there has one obvious place to land here. */

export const SDK_LANGUAGES = [
  "Python",
  "TypeScript",
  "Go",
  "Rust",
  "CLI",
] as const;

export type SdkLanguage = (typeof SDK_LANGUAGES)[number];

export const isSdkLanguage = (value: unknown): value is SdkLanguage =>
  SDK_LANGUAGES.includes(value as SdkLanguage);

/* grad server/api/src/catalog.ts (BUILTIN_MODELS). */
export type CatalogModel = {
  id: string;
  price: number;
  maxContext: number;
  defaultFor: RecipeKind[];
};

export type RecipeKind =
  | "sft"
  | "dpo"
  | "router"
  | "decision"
  | "cartridge"
  | "embedding"
  | "distill"
  | "reward";

export const CATALOG: CatalogModel[] = [
  {
    id: "qwen/qwen3-0.6b",
    price: 0.15,
    maxContext: 32_768,
    defaultFor: ["router"],
  },
  { id: "qwen/qwen3-1.7b", price: 0.22, maxContext: 32_768, defaultFor: [] },
  {
    id: "qwen/qwen3-4b",
    price: 0.3,
    maxContext: 32_768,
    defaultFor: ["distill"],
  },
  {
    id: "qwen/qwen3-8b",
    price: 0.4,
    maxContext: 32_768,
    defaultFor: ["sft", "dpo", "cartridge", "reward"],
  },
  { id: "qwen/qwen3-14b", price: 0.7, maxContext: 32_768, defaultFor: [] },
  { id: "qwen/qwen3-32b", price: 1.2, maxContext: 32_768, defaultFor: [] },
  {
    id: "gradiated/linden-1",
    price: 0.2,
    maxContext: 16_384,
    defaultFor: ["decision"],
  },
  {
    id: "baai/bge-small-en-v1.5",
    price: 0.08,
    maxContext: 512,
    defaultFor: ["embedding"],
  },
];

export const catalogModel = (id: string): CatalogModel =>
  CATALOG.find((model) => model.id === id) ?? CATALOG[3];

export const defaultModelFor = (kind: RecipeKind): CatalogModel =>
  CATALOG.find((model) => model.defaultFor.includes(kind)) ?? CATALOG[3];

/* grad server/api/src/planner.ts: estimateTextTokens and renderMessages. */
export const estimateTextTokens = (text: string): number => {
  const trimmed = text.trim();
  if (!trimmed) return 0;

  return Math.max(1, Math.ceil(trimmed.length / 4));
};

export type ChatMessage = {
  role: "system" | "user" | "assistant" | "tool";
  content: string;
  train?: boolean;
};

export type RenderOptions = {
  train_on: "last" | "all_assistant";
  thinking: "auto" | "on" | "off";
  preserve_thinking: boolean;
};

export type RenderedSpan = {
  text: string;
  trained: boolean;
  tokens: number;
  kind: "header" | "body";
  message: number;
  stripped?: string;
};

export type Rendered =
  | {
      ok: true;
      spans: RenderedSpan[];
      totalTokens: number;
      trainedTokens: number;
    }
  | { ok: false; error: string };

const THINK = /<think>[\s\S]*?<\/think>\s*/g;

export const renderMessages = (
  recordId: string,
  messages: readonly ChatMessage[],
  options: RenderOptions,
): Rendered => {
  let lastAssistant = -1;
  messages.forEach((message, index) => {
    if (message.role === "assistant") lastAssistant = index;
  });

  const spans: RenderedSpan[] = [];
  let totalTokens = 0;
  let trainedTokens = 0;

  for (const [index, message] of messages.entries()) {
    const isAssistant = message.role === "assistant";
    const isLast = index === lastAssistant;
    const trained =
      message.train ??
      (isAssistant && (options.train_on === "all_assistant" || isLast));

    if (trained && isAssistant) {
      const hasThink = /<think>[\s\S]*?<\/think>/.test(message.content);
      if (options.thinking === "off" && hasThink) {
        return {
          ok: false,
          error: `Record '${recordId}' contains a <think> block but thinking='off'.`,
        };
      }
      if (options.thinking === "on" && !hasThink) {
        return {
          ok: false,
          error: `Record '${recordId}' has no <think> block but thinking='on'.`,
        };
      }
    }

    const strip = isAssistant && !isLast && !options.preserve_thinking;
    const content = strip
      ? message.content.replace(THINK, "")
      : message.content;
    const stripped = strip ? (message.content.match(THINK) ?? []).join("") : "";
    const header = `<|im_start|>${message.role}\n`;
    const body = `${content}<|im_end|>\n`;
    const headerTokens = estimateTextTokens(header) + 2;
    const bodyTokens = estimateTextTokens(body) + 1;

    spans.push({
      text: header,
      trained: false,
      tokens: headerTokens,
      kind: "header",
      message: index,
    });
    spans.push({
      text: body,
      trained,
      tokens: bodyTokens,
      kind: "body",
      message: index,
      stripped: stripped || undefined,
    });
    totalTokens += headerTokens + bodyTokens;
    if (trained) trainedTokens += bodyTokens;
  }

  return { ok: true, spans, totalTokens, trainedTokens };
};

/* grad server/api/src/planner.ts: split, steps, tokens and cost. */
export type PlanInput = {
  records: number;
  tokensPerRecord: number;
  epochs: number;
  batchSize: number;
  evalFraction: number;
  price: number;
  maxCostUsd: number | null;
};

export type PlanEstimate = {
  trainRecords: number;
  evalRecords: number;
  steps: number;
  tokens: number;
  costUsd: number;
  warnings: string[];
};

export const estimatePlan = (input: PlanInput): PlanEstimate => {
  const evalRecords = Math.round(input.records * input.evalFraction);
  const trainRecords = Math.max(input.records - evalRecords, 1);
  const steps = Math.max(
    1,
    Math.ceil((trainRecords * input.epochs) / input.batchSize),
  );
  const tokens = trainRecords * input.tokensPerRecord * input.epochs;
  const costUsd = Number(((tokens / 1_000_000) * input.price).toFixed(4));
  const warnings: string[] = [];

  if (steps < 100) {
    const suggested = Math.max(
      1,
      Math.floor((trainRecords * input.epochs) / 100),
    );
    warnings.push(
      `${steps} steps is below the 100 we recommend; use batch_size=${suggested} or more epochs/data.`,
    );
  }
  if (evalRecords === 0) {
    warnings.push(
      "The eval split is empty; eval metrics will be unavailable. Add records or raise split.eval_fraction.",
    );
  }
  if (input.maxCostUsd !== null && costUsd > input.maxCostUsd) {
    warnings.push(
      `Estimated cost ($${costUsd.toFixed(2)}) exceeds max_cost_usd ($${input.maxCostUsd.toFixed(2)}); the run will stop early with status stopped_budget.`,
    );
  }

  return { trainRecords, evalRecords, steps, tokens, costUsd, warnings };
};

/* grad cli/src/output.rs: thousands, compact and usd. */
export const thousands = (value: number): string =>
  Math.round(value).toLocaleString("en-US");

export const compact = (value: number): string => {
  if (value >= 1e9) return `${(value / 1e9).toFixed(1)}B`;
  if (value >= 1e6) return `${(value / 1e6).toFixed(1)}M`;
  if (value >= 1e3) return `${(value / 1e3).toFixed(1)}k`;
  return String(Math.round(value));
};

export const usd = (value: number): string =>
  value !== 0 && Math.abs(value) < 0.01
    ? `$${value.toFixed(4)}`
    : `$${value.toFixed(2)}`;

/* A deterministic illustration for the router page, not a measurement. */
export type RouterPrompt = { p: number; smallOk: boolean; largeOk: boolean };

const mulberry32 = (seed: number) => () => {
  let t = (seed += 0x6d2b79f5);
  t = Math.imul(t ^ (t >>> 15), t | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};

export const illustrativeRouterPrompts = (count = 200): RouterPrompt[] => {
  const random = mulberry32(7);

  return Array.from({ length: count }, () => {
    const difficulty = random();
    const smallChance = Math.max(0.04, 0.98 - difficulty * 1.05);
    const largeChance = Math.max(0.55, 0.97 - difficulty * 0.3);
    const p = Math.min(
      0.99,
      Math.max(0.01, smallChance + (random() - 0.5) * 0.25),
    );

    return {
      p,
      smallOk: random() < smallChance,
      largeOk: random() < largeChance,
    };
  });
};

export type RouterPoint = {
  threshold: number;
  offload: number;
  quality: number;
  relativeCost: number;
};

export const routerPoint = (
  prompts: readonly RouterPrompt[],
  threshold: number,
  smallCost: number,
  largeCost: number,
): RouterPoint => {
  let offloaded = 0;
  let correct = 0;

  for (const prompt of prompts) {
    const small = prompt.p >= threshold;
    if (small) offloaded += 1;
    if (small ? prompt.smallOk : prompt.largeOk) correct += 1;
  }

  const offload = offloaded / prompts.length;
  const cost = offload * smallCost + (1 - offload) * largeCost;

  return {
    threshold,
    offload,
    quality: correct / prompts.length,
    relativeCost: cost / largeCost,
  };
};

export const routerCurve = (
  prompts: readonly RouterPrompt[],
  smallCost: number,
  largeCost: number,
): RouterPoint[] =>
  Array.from({ length: 101 }, (_, i) =>
    routerPoint(prompts, 1 - i / 100, smallCost, largeCost),
  );

/* The operating point RouterRecipe picks: the most offload whose quality
   stays within max_quality_drop of always calling the fallback. */
export const operatingPoint = (
  curve: readonly RouterPoint[],
  maxQualityDrop: number,
): RouterPoint => {
  const fallback = curve[0];
  const admissible = curve.filter(
    (point) => fallback.quality - point.quality <= maxQualityDrop + 1e-9,
  );

  return admissible.reduce(
    (best, point) => (point.offload > best.offload ? point : best),
    fallback,
  );
};
