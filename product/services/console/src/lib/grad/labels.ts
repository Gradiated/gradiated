import type {
  EvalStatus,
  InterruptionReason,
  RecipeKind,
  RunPhase,
  RunStatus,
} from "@/lib/grad/types";

export type Tone = "neutral" | "active" | "success" | "warning" | "danger";

export const RUN_STATUS: Record<RunStatus, { label: string; tone: Tone }> = {
  queued: { label: "Queued", tone: "neutral" },
  running: { label: "Running", tone: "active" },
  completed: { label: "Completed", tone: "success" },
  failed: { label: "Failed", tone: "danger" },
  cancelled: { label: "Cancelled", tone: "neutral" },
  stopped_budget: { label: "Stopped at cost cap", tone: "warning" },
  stopped_balance: { label: "Stopped: balance", tone: "warning" },
};

export const EVAL_STATUS: Record<EvalStatus, { label: string; tone: Tone }> = {
  queued: { label: "Queued", tone: "neutral" },
  running: { label: "Running", tone: "active" },
  awaiting_scores: { label: "Awaiting scores", tone: "active" },
  completed: { label: "Completed", tone: "success" },
  failed: { label: "Failed", tone: "danger" },
  cancelled: { label: "Cancelled", tone: "neutral" },
};

export const IMPORT_STATUS = {
  queued: { label: "Queued", tone: "neutral" },
  running: { label: "Importing", tone: "active" },
  completed: { label: "Completed", tone: "success" },
  failed: { label: "Failed", tone: "danger" },
} as const satisfies Record<string, { label: string; tone: Tone }>;

export const PHASE_LABEL: Record<RunPhase, string> = {
  queued: "Queued",
  waiting_for_compute: "Waiting for compute",
  starting: "Starting",
  loading_model: "Loading model",
  training: "Training",
  evaluating: "Evaluating",
  checkpointing: "Saving checkpoint",
  uploading: "Uploading artifact",
  completing: "Finishing",
};

export const INTERRUPTION_LABEL: Record<InterruptionReason, string> = {
  lease_lost: "Worker lost",
  compute_reclaimed: "Compute reclaimed",
  worker_error: "Worker error",
  oom: "Out of GPU memory",
};

export const RECIPE_LABEL: Record<RecipeKind, string> = {
  sft: "SFT",
  dpo: "DPO",
  router: "Router",
  decision: "Decision",
  cartridge: "Cartridge",
  embedding: "Embedding",
  distill: "Distillation",
  reward: "Reward model",
  grpo: "GRPO",
};

export const FORMAT_LABEL: Record<string, string> = {
  peft_lora: "LoRA adapter",
  merged_safetensors: "Merged weights",
  prefix_kv: "Prefix KV",
  cartridge: "Cartridge",
  encoder_safetensors: "Encoder",
  router_bundle: "Router bundle",
  decision_bundle: "Decision bundle",
  reward_bundle: "Reward bundle",
  reference: "Reference",
};

export const DEPLOYABLE_FORMATS: ReadonlySet<string> = new Set([
  "peft_lora",
  "cartridge",
]);

const TERMINAL_RUN: ReadonlySet<RunStatus> = new Set([
  "completed",
  "failed",
  "cancelled",
  "stopped_budget",
  "stopped_balance",
]);

export const isTerminalRun = (status: RunStatus) => TERMINAL_RUN.has(status);

export const canResumeRun = (status: RunStatus) =>
  status !== "completed" && isTerminalRun(status);

export const isTerminalEval = (status: EvalStatus) =>
  status === "completed" || status === "failed" || status === "cancelled";
