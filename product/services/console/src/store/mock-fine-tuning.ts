// UX MOCK — fake, in-memory, client-only state for the task fine-tuning console
// (docs/TASK_FINE_TUNING_FROM_TRACES_PLAN.md). Shapes mirror the plan's data model and
// contracts field-for-field (snake_case, nano-USD, ISO timestamps) so the real pages can swap
// this store for queries without changing the components. No network, no real training.
// Safe to delete wholesale.
import { create } from "zustand";

// ---------------------------------------------------------------------------
// §2.1.1 global constants (worker configuration, not customer settings)
// ---------------------------------------------------------------------------

export const TRACE_CAPTURE_WEEKLY_CAP = 500;
export const TRAINING_TRACE_THRESHOLD = 500;
/** Frontier judges for customer-facing evaluation (training rewards use an open judge we host). */
export const EVALUATION_JUDGE_ALLOWLIST = [
  "openai/gpt-5.6-sol",
  "openai/gpt-5",
  "anthropic/claude-fable-5-1",
  "anthropic/claude-opus-5",
  "anthropic/claude-sonnet-5",
] as const;
export type EvaluationJudge = (typeof EVALUATION_JUDGE_ALLOWLIST)[number];

// ---------------------------------------------------------------------------
// §2.1 PostgreSQL rows
// ---------------------------------------------------------------------------

/** `workspaces` (identity plus the columns this feature adds). */
export interface WorkspaceRow {
  id: string;
  organization_id: string;
  name: string;
  trace_capture_enabled: boolean;
  evaluation_judge: EvaluationJudge;
}

/** `models.adapter` jsonb. */
export interface AdapterArtifact {
  format: "peft_lora";
  artifact_uri: string;
  sha256: string;
  size_bytes: number;
  rank: number;
  name: string;
  source: "trained" | "uploaded";
}

/** `models` — catalog models (workspace_id null) and fine-tuned versions (task_id set). */
export interface ModelRow {
  id: string;
  status: "available" | "unavailable";
  trainable: boolean;
  workspace_id: string | null;
  task_id: string | null;
  base_model_id: string | null;
  training_run_id: string | null;
  adapter: AdapterArtifact | null;
  created_at: string;
}

/** `tasks`. */
export interface TaskRow {
  id: string;
  workspace_id: string;
  slug: string;
  base_model_id: string;
  /** The model this task's versions are judged, costed and timed against. Set from the first
   *  request's model when the task is created; editable in the task's Settings; every later run uses it. */
  comparison_model_id: string;
  /** System-written by the automation loop from trailing 7-day volume; never customer-edited. */
  trace_capture_rate: number;
  /** The version the task name resolves to. Null until a member promotes one; promotion is manual. */
  production_model_id: string | null;
  production_changed_at: string | null;
  created_at: string;
  updated_at: string;
}

export type RunStage =
  | "queued"
  | "building_dataset"
  | "awaiting_capacity"
  | "training"
  | "verifying"
  | "publishing"
  | "evaluating"
  | "cancelling"
  | "succeeded"
  | "failed"
  | "cancelled";

export const STAGE_ORDER: RunStage[] = [
  "queued",
  "building_dataset",
  "awaiting_capacity",
  "training",
  "verifying",
  "publishing",
  "evaluating",
  "succeeded",
];

export const STAGE_LABEL: Record<RunStage, string> = {
  queued: "Queued",
  building_dataset: "Building dataset",
  awaiting_capacity: "Waiting for capacity",
  training: "Training",
  verifying: "Verifying",
  publishing: "Publishing",
  evaluating: "Evaluating",
  cancelling: "Cancelling",
  succeeded: "Succeeded",
  failed: "Failed",
  cancelled: "Cancelled",
};

export const TERMINAL_STAGES: RunStage[] = ["succeeded", "failed", "cancelled"];

/** `training_runs.dataset` jsonb. */
export interface RunDataset {
  oldest_trace_at: string;
  newest_trace_at: string;
  /** Complete captured requests that met the eligibility predicate (DATA-01). */
  usable: number;
  deduplicated: number;
  train: number;
  validation: number;
  holdout: number;
  train_sha256: string;
  holdout_sha256: string;
}

/**
 * EVAL-02: the candidate against one comparator. Fractions are averaged over session
 * groups with equal weight and sum to 1. `unresolved` is where the two judge orderings
 * disagreed or abstained; it is shown, never folded into a loss.
 */
export interface JudgeOutcome {
  comparator_model_id: string;
  groups: number;
  examples: number;
  win: number;
  tie: number;
  loss: number;
  unresolved: number;
  /** `(win + 0.5·tie) / (1 − unresolved)`; null when nothing resolved. */
  conditional_score: number | null;
  /** 95% interval from resampling whole groups; null below two groups. */
  interval: [number, number] | null;
}

/** EVAL-02 `EvaluationSummary`. No pass mark, no recommendation, no gate. */
export interface EvaluationSummary {
  schema_version: 3;
  holdout_groups: number;
  holdout_examples: number;
  comparison_model_id: string;
  judge_model_id: string;
  rubric_version: string;
  /** Against the provider model the task replaces (a fresh call, paid by Gradiated). The only judged comparison. */
  vs_comparison: JudgeOutcome;
  cost_per_request_nano_usd: { fine_tuned: number; comparison: number };
  /** Both measured at the gateway (EVAL-03). */
  output_tokens_per_second: { fine_tuned: number; comparison: number };
  /** Deterministic format or protocol failures; shown separately from the judge. */
  error_rate: number;
  computed_at: string;
}

/** `training_runs.evaluation` jsonb. */
export interface RunEvaluation {
  judge: string;
  holdout: number;
  summary: EvaluationSummary;
}

/** `training_runs` — the 13 columns. Everything else is derived from the run log. */
export interface TrainingRunRow {
  id: string;
  workspace_id: string;
  task_id: string;
  trigger: "automation" | "manual";
  base_model_id: string;
  stage: RunStage;
  dataset: RunDataset | null;
  evaluation: RunEvaluation | null;
  provider_job_id: string | null;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// §4.2 TrainingRunEvent — one JSONL line each in training-logs/<run_id>/run.jsonl
// ---------------------------------------------------------------------------

interface EventEnvelope {
  schema_version: 1;
  /** RUN-01: a lost-host retry is a new attempt; `seq` is per source and attempt. */
  attempt: number;
  seq: number;
  at: string;
  source: "control_plane" | "trainer";
  metadata?: Record<string, unknown>;
}

export type TrainerStage =
  "starting" | "preparing_data" | "training" | "checkpointing" | "uploading";

export type TrainingRunEventPayload =
  | {
      type: "run_created";
      trigger: "automation" | "manual";
      task_id: string;
      base_model_id: string;
      requested_by?: string;
    }
  | { type: "stage_entered"; stage: RunStage }
  | {
      type: "dataset_built";
      usable: number;
      deduplicated: number;
      train: number;
      validation: number;
      holdout: number;
      oldest_trace_at: string;
      newest_trace_at: string;
      train_sha256: string;
      holdout_sha256: string;
    }
  | {
      type: "capacity_granted";
      host_id: string;
      gpu: { type: string; count: number };
    }
  | {
      type: "job_submitted";
      runner: string;
      provider_job_id: string;
      host_id: string;
      gpu: { type: string; count: number };
    }
  | { type: "job_status"; state: string; message?: string }
  | { type: "model_reserved"; model_id: string }
  | {
      type: "artifact_verified";
      model_id: string;
      sha256: string;
      size_bytes: number;
    }
  | { type: "adapter_loaded"; host_id: string }
  | { type: "evaluation_progress"; completed: number; total: number }
  | {
      type: "evaluation_completed";
      judge: string;
      groups: number;
      win: number;
      tie: number;
      loss: number;
      unresolved: number;
    }
  | { type: "published"; model_id: string }
  | { type: "cancel_requested"; requested_by: string }
  | {
      type: "run_finished";
      stage: "succeeded" | "failed" | "cancelled";
      error_code?: string;
      message?: string;
    }
  | { type: "note"; level: "info" | "warning" | "error"; message: string }
  | {
      type: "trainer_started";
      gpu: string;
      image_digest: string;
      recipe: string;
    }
  | { type: "trainer_stage"; stage: TrainerStage }
  | {
      type: "trainer_progress";
      step: number;
      total_steps: number;
      loss: number;
      /** Mean judged reward of the step's rollouts (GRPO). */
      mean_reward: number;
      tokens_per_second: number;
      eta_seconds: number;
    }
  | { type: "trainer_checkpoint"; step: number; sha256: string }
  | {
      type: "trainer_artifact_uploaded";
      name: string;
      sha256: string;
      size_bytes: number;
    }
  | { type: "trainer_finished"; manifest_sha256: string }
  | {
      type: "trainer_failed";
      error_code:
        | "dataset_invalid"
        | "oom"
        | "judge_unavailable"
        | "upload_failed"
        | "deadline"
        | "internal";
      message: string;
    };

export type TrainingRunEvent = EventEnvelope & TrainingRunEventPayload;

// ---------------------------------------------------------------------------
// §2.2 ClickHouse traces (one row per generation) joined with `generations`
// ---------------------------------------------------------------------------

export interface TraceGenerationRow {
  // traces
  id: string;
  trace_id: string;
  organization_id: string;
  workspace_id: string;
  task: string;
  protocol: "openai_chat" | "anthropic_messages";
  route_mode: "passthrough" | "hosted";
  request_hash: string;
  request_truncated: boolean;
  response_truncated: boolean;
  response_status: number;
  response_streamed: boolean;
  captured_at: string;
  // generations (joined by id): what the list and detail read
  model: string;
  latency_ms: number;
  input_tokens: number;
  output_tokens: number;
  cost_nano_usd: number;
}

/** Normalized conversation for the trace detail (traffic/service.ts builds it from the bodies). */
export interface TraceMessage {
  role: "system" | "user" | "assistant" | "tool";
  content?: string;
  tool_call?: { name: string; arguments: string };
  tool_name?: string;
  /** For assistant messages: the generation that produced it. */
  generation_id?: string;
}

// ---------------------------------------------------------------------------
// Derived views (what the services/contracts return)
// ---------------------------------------------------------------------------

/** `tasks.ts` task-with-stats: all computed from ClickHouse `generations`/`traces`. */
export interface TaskStats {
  requests_7d: number;
  tokens_7d: number;
  provider_spend_7d_nano_usd: number | null;
  traces_this_week: number;
  usable_traces_since_last_run: number;
}

/** `traffic.ts` trace summary (one row of the trace list). */
export interface TraceSummary {
  trace_id: string;
  started_at: string;
  generation_count: number;
  duration_ms: number;
  cost_nano_usd: number;
  /** true when `trace_id` is a generation id, i.e. nothing grouped it. */
  single_generation: boolean;
}

export interface RunTimelineEntry {
  stage: RunStage;
  entered_at: string;
}

export interface RunProgress {
  step: number;
  total_steps: number;
  loss: number;
  mean_reward: number;
  tokens_per_second: number;
  eta_seconds: number;
}

/** One line of evaluation/<run_id>/results.jsonl as paged by the API. */
export interface EvaluationResultLine {
  index: number;
  request_preview: string;
  comparison_response: string;
  fine_tuned_response: string;
  verdict: "better" | "equivalent" | "worse" | "unresolved";
}

/** GET P/tasks/{task_id}/models — a version with what the console needs joined in. */
export interface VersionView {
  model: ModelRow;
  run: TrainingRunRow;
  summary: EvaluationSummary;
  workspace_name: string;
  /** `tasks.production_model_id` points at this version. */
  is_production: boolean;
  /** Trained after the production version, so a regression that was not promoted stays visible. */
  newer_than_production: boolean;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const ORGANIZATION_ID = "0198c36f-0000-7000-8000-00000000a001";
const WORKSPACE_ID = "0198c36f-0000-7000-8000-00000000b001";
const WORKSPACE_NAME = "default";
export const BASE_MODEL_ID = "google/gemma-4-31b-it";
const LORA_DEPLOYMENT_ID = "0198c36f-9b6a-7000-8000-0000000000a4";

const iso = (offsetMs: number) => new Date(Date.now() + offsetMs).toISOString();
const days = (n: number) => n * 24 * 60 * 60 * 1000;
const hours = (n: number) => n * 60 * 60 * 1000;
const minutes = (n: number) => n * 60 * 1000;
export const NANO = 1_000_000_000;
const sha = (seed: string) => {
  let h = 0x811c9dc5;
  for (const ch of seed) h = Math.imul(h ^ ch.charCodeAt(0), 0x01000193) >>> 0;
  return h.toString(16).padStart(8, "0").repeat(8);
};

/** USD per million tokens (input, output) — stand-in for the OpenRouter list-price snapshot. */
const LIST_PRICE_PER_M: Record<string, [number, number]> = {
  "gpt-4o": [2.5, 10],
  "gpt-4o-mini": [0.15, 0.6],
  "claude-3-5-sonnet-20241022": [3, 15],
  "claude-3-5-haiku-20241022": [0.8, 4],
  [BASE_MODEL_ID]: [0.2, 0.6],
};
/** Provider models at list price; fine-tuned versions at their base model's price. */
export const priceForModel = (
  modelId: string,
  baseModelId = BASE_MODEL_ID,
): [number, number] =>
  LIST_PRICE_PER_M[modelId] ?? LIST_PRICE_PER_M[baseModelId] ?? [0, 0];
const costNano = (
  modelId: string,
  inputTokens: number,
  outputTokens: number,
) => {
  const [inP, outP] = priceForModel(modelId);
  return Math.round(
    ((inputTokens * inP + outputTokens * outP) / 1_000_000) * NANO,
  );
};

export const versionIdFor = (slug: string, at: Date) =>
  `${slug}-${at.toISOString().slice(0, 10).replace(/-/g, "")}`;

// ---------------------------------------------------------------------------
// Seed: traces
// ---------------------------------------------------------------------------

interface TraceTemplate {
  header: boolean;
  protocol: TraceGenerationRow["protocol"];
  generations: { model: string; latency_ms: number }[];
  messages: Omit<TraceMessage, "generation_id">[];
}

const SUPPORT_SYSTEM =
  "You are a support triage agent. Classify the ticket by calling classify_ticket, then write a short acknowledgement to the customer.";

const supportTriageTemplates: TraceTemplate[] = [
  {
    header: false,
    protocol: "openai_chat",
    generations: [
      { model: "gpt-4o", latency_ms: 640 },
      { model: "gpt-4o", latency_ms: 910 },
    ],
    messages: [
      { role: "system", content: SUPPORT_SYSTEM },
      {
        role: "user",
        content:
          "Hey, I upgraded to the Pro plan yesterday but I'm still being charged the old rate and the invoice shows a $0 line item for the upgrade. Can you fix the billing?",
      },
      {
        role: "assistant",
        tool_call: {
          name: "classify_ticket",
          arguments: '{"category":"billing","priority":"high"}',
        },
      },
      {
        role: "tool",
        tool_name: "classify_ticket",
        content:
          '{"ok":true,"ticket_id":48213,"queue":"billing","sla_hours":4}',
      },
      {
        role: "assistant",
        content:
          "Thanks for flagging this — I've routed it to our billing team as high priority (ticket #48213). They'll correct the plan rate and reissue the invoice; you should hear back within 4 hours.",
      },
    ],
  },
  {
    header: true,
    protocol: "openai_chat",
    generations: [
      { model: "gpt-4o", latency_ms: 580 },
      { model: "gpt-4o-mini", latency_ms: 410 },
    ],
    messages: [
      { role: "system", content: SUPPORT_SYSTEM },
      {
        role: "user",
        content:
          "The export button on the dashboard just spins forever and never downloads the CSV. Happens every time on Chrome and Safari.",
      },
      {
        role: "assistant",
        tool_call: {
          name: "classify_ticket",
          arguments: '{"category":"bug_report","priority":"medium"}',
        },
      },
      {
        role: "tool",
        tool_name: "classify_ticket",
        content:
          '{"ok":true,"ticket_id":48219,"queue":"engineering","sla_hours":24}',
      },
      {
        role: "assistant",
        content:
          "Sorry about that — I've logged it as a bug for the dashboard team (ticket #48219). In the meantime, the CSV is also available from Reports → Export history if you need the data today.",
      },
    ],
  },
  {
    header: false,
    protocol: "openai_chat",
    generations: [{ model: "gpt-4o", latency_ms: 520 }],
    messages: [
      { role: "system", content: SUPPORT_SYSTEM },
      { role: "user", content: "How do I add a second admin to my workspace?" },
      {
        role: "assistant",
        tool_call: {
          name: "classify_ticket",
          arguments: '{"category":"account_access","priority":"low"}',
        },
      },
    ],
  },
];

const SQL_SYSTEM =
  "You answer analytics questions by writing PostgreSQL and calling run_sql. Schema: orders(id, customer_id, status, total_cents, created_at), customers(id, email, plan).";

const sqlGenerationTemplates: TraceTemplate[] = [
  {
    header: true,
    protocol: "anthropic_messages",
    generations: [
      { model: "claude-3-5-sonnet-20241022", latency_ms: 1180 },
      { model: "claude-3-5-sonnet-20241022", latency_ms: 1320 },
      { model: "claude-3-5-haiku-20241022", latency_ms: 540 },
    ],
    messages: [
      { role: "system", content: SQL_SYSTEM },
      {
        role: "user",
        content:
          "What was revenue from completed orders in the last 30 days, by day?",
      },
      {
        role: "assistant",
        tool_call: {
          name: "run_sql",
          arguments:
            "{\"query\":\"SELECT date_trunc('day', created_at) AS day, SUM(total) AS revenue FROM orders WHERE status = 'completed' AND created_at >= now() - interval '30 days' GROUP BY 1 ORDER BY 1\"}",
        },
      },
      {
        role: "tool",
        tool_name: "run_sql",
        content:
          '{"error":"column \\"total\\" does not exist","hint":"Perhaps you meant total_cents"}',
      },
      {
        role: "assistant",
        tool_call: {
          name: "run_sql",
          arguments:
            "{\"query\":\"SELECT date_trunc('day', created_at) AS day, SUM(total_cents) / 100.0 AS revenue FROM orders WHERE status = 'completed' AND created_at >= now() - interval '30 days' GROUP BY 1 ORDER BY 1\"}",
        },
      },
      {
        role: "tool",
        tool_name: "run_sql",
        content:
          '{"rows":30,"sample":[{"day":"2026-08-05","revenue":18420.50},{"day":"2026-08-06","revenue":17210.00}]}',
      },
      {
        role: "assistant",
        content:
          "Here's completed-order revenue per day for the last 30 days (30 rows). Revenue ranged from about $14.9k to $21.3k per day, averaging roughly $18.1k.",
      },
    ],
  },
  {
    header: false,
    protocol: "anthropic_messages",
    generations: [
      { model: "claude-3-5-sonnet-20241022", latency_ms: 1040 },
      { model: "claude-3-5-sonnet-20241022", latency_ms: 880 },
    ],
    messages: [
      { role: "system", content: SQL_SYSTEM },
      {
        role: "user",
        content:
          "Emails of pro-plan customers with more than 3 orders this month?",
      },
      {
        role: "assistant",
        tool_call: {
          name: "run_sql",
          arguments:
            "{\"query\":\"SELECT c.email FROM customers c JOIN orders o ON o.customer_id = c.id WHERE c.plan = 'pro' AND o.created_at >= date_trunc('month', now()) GROUP BY c.email HAVING COUNT(*) > 3\"}",
        },
      },
      {
        role: "tool",
        tool_name: "run_sql",
        content:
          '{"rows":12,"sample":[{"email":"ana@acme.io"},{"email":"dev@northwind.co"}]}',
      },
      {
        role: "assistant",
        content:
          "12 pro-plan customers placed more than 3 orders this month. First few: ana@acme.io, dev@northwind.co…",
      },
    ],
  },
];

const emailDraftTemplates: TraceTemplate[] = [
  {
    header: false,
    protocol: "openai_chat",
    generations: [{ model: "gpt-4o-mini", latency_ms: 720 }],
    messages: [
      {
        role: "system",
        content: "Draft a short, friendly reply to the customer email below.",
      },
      {
        role: "user",
        content:
          "Subject: Refund status?\n\nHi, I asked for a refund 5 days ago and haven't heard back. Order #48213. Can someone update me?",
      },
      {
        role: "assistant",
        content:
          "Hi there, thanks for your patience and sorry for the delay. I checked order #48213 and your refund was approved — it should land in your account within 3–5 business days. Let me know if it hasn't shown up by then!",
      },
    ],
  },
];

const buildTraces = (
  taskSlug: string,
  templates: TraceTemplate[],
  count: number,
): {
  rows: TraceGenerationRow[];
  conversations: Record<string, TraceMessage[]>;
} => {
  const rows: TraceGenerationRow[] = [];
  const conversations: Record<string, TraceMessage[]> = {};
  for (let i = 0; i < count; i++) {
    const template = templates[i % templates.length]!;
    const startedAt = Date.now() - hours(i * 3 + 1);
    const errored = i % 11 === 3;
    const generationIds = template.generations.map(
      (_, g) => `gen_${sha(`${taskSlug}-${i}-${g}`).slice(0, 16)}`,
    );
    // A header-grouped session has an opaque customer id; otherwise trace_id is the first generation's id.
    const traceId =
      template.header && template.generations.length > 1
        ? `tr_${sha(`${taskSlug}-${i}`).slice(0, 12)}`
        : generationIds[0]!;
    let offset = 0;
    template.generations.forEach(({ model, latency_ms }, g) => {
      const inputTokens = 140 + g * 90;
      const outputTokens = 18 + g * 30;
      rows.push({
        id: generationIds[g]!,
        trace_id: traceId,
        organization_id: ORGANIZATION_ID,
        workspace_id: WORKSPACE_ID,
        task: taskSlug,
        protocol: template.protocol,
        route_mode: "passthrough",
        request_hash: sha(`${taskSlug}-${i}-${g}-req`),
        request_truncated: false,
        response_truncated: false,
        response_status:
          errored && g === template.generations.length - 1 ? 429 : 200,
        response_streamed: g % 2 === 0,
        captured_at: new Date(startedAt + offset).toISOString(),
        model,
        latency_ms,
        input_tokens: inputTokens,
        output_tokens: outputTokens,
        cost_nano_usd: costNano(model, inputTokens, outputTokens),
      });
      offset += latency_ms + 120;
    });
    let g = 0;
    conversations[traceId] = template.messages.map((m) =>
      m.role === "assistant"
        ? { ...m, generation_id: generationIds[g++] ?? "" }
        : { ...m },
    );
  }
  return { rows, conversations };
};

// ---------------------------------------------------------------------------
// Seed: evaluation summaries
// ---------------------------------------------------------------------------

const outcome = (
  comparator: string,
  groups: number,
  examples: number,
  win: number,
  tie: number,
  unresolved: number,
): JudgeOutcome => {
  const loss = Number((1 - win - tie - unresolved).toFixed(3));
  const resolved = 1 - unresolved;
  const score = resolved > 0 ? (win + 0.5 * tie) / resolved : null;
  return {
    comparator_model_id: comparator,
    groups,
    examples,
    win,
    tie,
    loss,
    unresolved,
    conditional_score: score === null ? null : Number(score.toFixed(3)),
    interval:
      groups >= 2 && score !== null
        ? [
            Number(Math.max(0, score - 0.09).toFixed(3)),
            Number(Math.min(1, score + 0.08).toFixed(3)),
          ]
        : null,
  };
};

const buildEvaluation = (opts: {
  holdout: number;
  comparison_model_id: string;
  judge: string;
  strong: boolean;
  at: string;
}): EvaluationSummary => {
  const examples = opts.holdout;
  const groups = Math.max(1, Math.round(examples / 3.2));
  return {
    schema_version: 3,
    holdout_groups: groups,
    holdout_examples: examples,
    comparison_model_id: opts.comparison_model_id,
    judge_model_id: opts.judge,
    rubric_version: "rubric-v2",
    vs_comparison: opts.strong
      ? outcome(opts.comparison_model_id, groups, examples, 0.44, 0.34, 0.05)
      : outcome(opts.comparison_model_id, groups, examples, 0.3, 0.28, 0.08),
    cost_per_request_nano_usd: {
      fine_tuned: costNano(BASE_MODEL_ID, 150, 46),
      comparison: costNano(opts.comparison_model_id, 150, 46),
    },
    output_tokens_per_second: {
      fine_tuned: 112,
      comparison: opts.comparison_model_id.startsWith("claude") ? 58 : 71,
    },
    error_rate: opts.strong ? 0.01 : 0.04,
    computed_at: opts.at,
  };
};

const event = (
  seq: number,
  at: string,
  source: EventEnvelope["source"],
  payload: TrainingRunEventPayload,
  attempt = 1,
): TrainingRunEvent => ({
  schema_version: 1,
  attempt,
  seq,
  at,
  source,
  ...payload,
});

const datasetFor = (
  id: string,
  usable: number,
  oldestDaysAgo: number,
  newestDaysAgo: number,
  holdout?: number,
): RunDataset => {
  const h = holdout ?? Math.round(usable * 0.1);
  const validation = Math.round((usable - h) * 0.05);
  return {
    oldest_trace_at: iso(-days(oldestDaysAgo)),
    newest_trace_at: iso(-days(newestDaysAgo)),
    usable,
    deduplicated: usable,
    train: usable - h - validation,
    validation,
    holdout: h,
    train_sha256: sha(`${id}-train`),
    holdout_sha256: sha(`${id}-holdout`),
  };
};

const adapterFor = (modelId: string): AdapterArtifact => ({
  format: "peft_lora",
  artifact_uri: `s3://gradiated-prod-artifacts-us-east-1/adapters/${modelId}/adapter.tar.gz`,
  sha256: sha(`${modelId}-adapter`),
  size_bytes: 231_735_296,
  rank: 16,
  name: modelId,
  source: "trained",
});

const HOSTS = ["h200-nbs-03", "h200-nbs-07"];
const TOTAL_STEPS = 640;
const TRAINER_IMAGE = "sha256:4c1e…9b0f";
const RECIPE = "grpo-lora-v1";

const datasetBuilt = (ds: RunDataset): TrainingRunEventPayload => ({
  type: "dataset_built",
  usable: ds.usable,
  deduplicated: ds.deduplicated,
  train: ds.train,
  validation: ds.validation,
  holdout: ds.holdout,
  oldest_trace_at: ds.oldest_trace_at,
  newest_trace_at: ds.newest_trace_at,
  train_sha256: ds.train_sha256,
  holdout_sha256: ds.holdout_sha256,
});

const progressAt = (i: number): TrainingRunEventPayload => ({
  type: "trainer_progress",
  step: Math.round((TOTAL_STEPS * (i + 1)) / 10),
  total_steps: TOTAL_STEPS,
  loss: Number((0.9 * Math.pow(0.84, i + 1)).toFixed(3)),
  mean_reward: Number((0.41 + 0.045 * (i + 1)).toFixed(3)),
  tokens_per_second: 1312,
  eta_seconds: Math.max(0, (9 - i) * 360),
});

const fullRunLog = (
  run: TrainingRunRow,
  modelId: string,
  start: number,
  stepMs: number,
  ds: RunDataset,
  summary: EvaluationSummary,
): TrainingRunEvent[] => {
  let seq = 0;
  const t = (i: number, extra = 0) => iso(start + i * stepMs + extra);
  const cp = (at: string, p: TrainingRunEventPayload) =>
    event(++seq, at, "control_plane", p);
  const tr = (at: string, p: TrainingRunEventPayload) =>
    event(++seq, at, "trainer", p);
  const host = HOSTS[0]!;
  return [
    cp(t(0), {
      type: "run_created",
      trigger: run.trigger,
      task_id: run.task_id,
      base_model_id: run.base_model_id,
    }),
    cp(t(0, 1000), { type: "stage_entered", stage: "queued" }),
    cp(t(1), { type: "stage_entered", stage: "building_dataset" }),
    cp(t(1, 2000), {
      type: "note",
      level: "info",
      message: `scanned ${ds.usable + 41} captured requests since the last run, ${ds.usable} eligible (41 dropped: truncated or outcome unknown)`,
    }),
    cp(t(1, 9000), datasetBuilt(ds)),
    cp(t(2), { type: "stage_entered", stage: "awaiting_capacity" }),
    cp(t(2, 21_000), {
      type: "capacity_granted",
      host_id: host,
      gpu: { type: "NVIDIA H200", count: 8 },
    }),
    cp(t(3), { type: "stage_entered", stage: "training" }),
    cp(t(3, 500), { type: "model_reserved", model_id: modelId }),
    cp(t(3, 1200), {
      type: "job_submitted",
      runner: "nomad",
      provider_job_id: run.provider_job_id ?? "",
      host_id: host,
      gpu: { type: "NVIDIA H200", count: 8 },
    }),
    tr(t(3, 38_000), {
      type: "trainer_started",
      gpu: "8× NVIDIA H200 141GB",
      image_digest: TRAINER_IMAGE,
      recipe: RECIPE,
    }),
    tr(t(3, 52_000), { type: "trainer_stage", stage: "preparing_data" }),
    tr(t(3, 61_000), { type: "trainer_stage", stage: "training" }),
    ...Array.from({ length: 10 }, (_, i) => i).flatMap((i) => [
      tr(t(3, minutes(2 + i * 6)), progressAt(i)),
      ...((i + 1) % 2 === 0
        ? [
            tr(t(3, minutes(2 + i * 6) + 4000), {
              type: "trainer_checkpoint" as const,
              step: Math.round((TOTAL_STEPS * (i + 1)) / 10),
              sha256: sha(`${run.id}-ckpt-${i}`),
            }),
          ]
        : []),
    ]),
    tr(t(3, minutes(62)), { type: "trainer_stage", stage: "uploading" }),
    tr(t(3, minutes(63)), {
      type: "trainer_artifact_uploaded",
      name: "adapter.tar.gz",
      sha256: sha(`${run.id}-adapter`),
      size_bytes: 231_735_296,
    }),
    tr(t(3, minutes(63) + 4000), {
      type: "trainer_artifact_uploaded",
      name: "manifest.json",
      sha256: sha(`${run.id}-manifest`),
      size_bytes: 4_812,
    }),
    tr(t(3, minutes(63) + 5000), {
      type: "trainer_finished",
      manifest_sha256: sha(`${run.id}-manifest`),
    }),
    cp(t(3, minutes(64)), { type: "job_status", state: "complete" }),
    cp(t(4), { type: "stage_entered", stage: "verifying" }),
    cp(t(4, 41_000), {
      type: "artifact_verified",
      model_id: modelId,
      sha256: sha(`${run.id}-adapter`),
      size_bytes: 231_735_296,
    }),
    cp(t(5), { type: "stage_entered", stage: "publishing" }),
    cp(t(5, 12_000), { type: "adapter_loaded", host_id: HOSTS[0]! }),
    cp(t(5, 14_000), { type: "adapter_loaded", host_id: HOSTS[1]! }),
    cp(t(5, 15_000), { type: "published", model_id: modelId }),
    cp(t(6), { type: "stage_entered", stage: "evaluating" }),
    cp(t(6, 60_000), {
      type: "evaluation_progress",
      completed: Math.round(ds.holdout / 2),
      total: ds.holdout,
    }),
    cp(t(6, 120_000), {
      type: "evaluation_progress",
      completed: ds.holdout,
      total: ds.holdout,
    }),
    cp(t(6, 187_000), {
      type: "evaluation_completed",
      judge: summary.judge_model_id,
      groups: summary.holdout_groups,
      win: summary.vs_comparison.win,
      tie: summary.vs_comparison.tie,
      loss: summary.vs_comparison.loss,
      unresolved: summary.vs_comparison.unresolved,
    }),
    cp(t(7), { type: "stage_entered", stage: "succeeded" }),
    cp(t(7, 100), { type: "run_finished", stage: "succeeded" }),
  ];
};

/** A run that lost its host once, was retried on another, and hit its attempt deadline. */
const failedRunLog = (
  run: TrainingRunRow,
  start: number,
  stepMs: number,
  ds: RunDataset,
): TrainingRunEvent[] => {
  let seq = 0;
  const t = (i: number, extra = 0) => iso(start + i * stepMs + extra);
  const cp = (at: string, p: TrainingRunEventPayload, attempt = 1) =>
    event(++seq, at, "control_plane", p, attempt);
  const tr = (at: string, p: TrainingRunEventPayload, attempt = 1) =>
    event(++seq, at, "trainer", p, attempt);
  return [
    cp(t(0), {
      type: "run_created",
      trigger: run.trigger,
      task_id: run.task_id,
      base_model_id: run.base_model_id,
      requested_by: "josh@gradiated.com",
    }),
    cp(t(0, 1000), { type: "stage_entered", stage: "queued" }),
    cp(t(1), { type: "stage_entered", stage: "building_dataset" }),
    cp(t(1, 8000), datasetBuilt(ds)),
    cp(t(2), { type: "stage_entered", stage: "awaiting_capacity" }),
    cp(t(2, 9_000), {
      type: "capacity_granted",
      host_id: HOSTS[1]!,
      gpu: { type: "NVIDIA H200", count: 8 },
    }),
    cp(t(3), { type: "stage_entered", stage: "training" }),
    cp(t(3, 1200), {
      type: "job_submitted",
      runner: "nomad",
      provider_job_id: `training-${run.id.slice(-6)}-1`,
      host_id: HOSTS[1]!,
      gpu: { type: "NVIDIA H200", count: 8 },
    }),
    tr(t(3, 40_000), {
      type: "trainer_started",
      gpu: "8× NVIDIA H200 141GB",
      image_digest: TRAINER_IMAGE,
      recipe: RECIPE,
    }),
    tr(t(3, 61_000), { type: "trainer_stage", stage: "training" }),
    tr(t(3, minutes(2)), progressAt(0)),
    tr(t(3, minutes(8)), progressAt(1)),
    tr(t(3, minutes(8) + 4000), {
      type: "trainer_checkpoint",
      step: 128,
      sha256: sha(`${run.id}-ckpt-1`),
    }),
    cp(t(3, minutes(11)), { type: "job_status", state: "lost" }),
    cp(t(3, minutes(11) + 500), {
      type: "note",
      level: "warning",
      message: `host ${HOSTS[1]} stopped reporting; retrying once from the step-128 checkpoint on another host`,
    }),
    cp(
      t(3, minutes(12)),
      {
        type: "capacity_granted",
        host_id: HOSTS[0]!,
        gpu: { type: "NVIDIA H200", count: 8 },
      },
      2,
    ),
    cp(
      t(3, minutes(12) + 1200),
      {
        type: "job_submitted",
        runner: "nomad",
        provider_job_id: `training-${run.id.slice(-6)}-2`,
        host_id: HOSTS[0]!,
        gpu: { type: "NVIDIA H200", count: 8 },
      },
      2,
    ),
    tr(
      t(3, minutes(13)),
      {
        type: "trainer_started",
        gpu: "8× NVIDIA H200 141GB",
        image_digest: TRAINER_IMAGE,
        recipe: RECIPE,
      },
      2,
    ),
    tr(t(3, minutes(14)), { type: "trainer_stage", stage: "training" }, 2),
    tr(t(3, minutes(20)), progressAt(2), 2),
    tr(t(3, minutes(26)), progressAt(3), 2),
    tr(
      t(3, minutes(31)),
      {
        type: "trainer_failed",
        error_code: "deadline",
        message: "attempt deadline reached at step 256 of 640",
      },
      2,
    ),
    cp(t(3, minutes(31) + 500), { type: "job_status", state: "failed" }, 2),
    cp(t(3, minutes(32)), { type: "stage_entered", stage: "failed" }, 2),
    cp(
      t(3, minutes(32) + 500),
      {
        type: "run_finished",
        stage: "failed",
        error_code: "attempt_deadline",
        message: "The training attempt did not finish within its deadline.",
      },
      2,
    ),
  ];
};

interface Seed {
  workspace: WorkspaceRow;
  models: ModelRow[];
  tasks: TaskRow[];
  training_runs: TrainingRunRow[];
  run_logs: Record<string, TrainingRunEvent[]>;
  traces: TraceGenerationRow[];
  conversations: Record<string, TraceMessage[]>;
  stats: Record<string, TaskStats>;
}

const seed = (): Seed => {
  const workspace: WorkspaceRow = {
    id: WORKSPACE_ID,
    organization_id: ORGANIZATION_ID,
    name: WORKSPACE_NAME,
    trace_capture_enabled: true,
    evaluation_judge: "openai/gpt-5.6-sol",
  };
  const catalog = (
    id: string,
    trainable: boolean,
    ageDays: number,
  ): ModelRow => ({
    id,
    status: "available",
    trainable,
    workspace_id: null,
    task_id: null,
    base_model_id: null,
    training_run_id: null,
    adapter: null,
    created_at: iso(-days(ageDays)),
  });
  const models: ModelRow[] = [
    catalog(BASE_MODEL_ID, true, 120),
    catalog("z-ai/glm-5.3-flash", false, 90),
  ];

  const task = (
    n: string,
    slug: string,
    rate: number,
    createdDaysAgo: number,
    comparison: string,
  ): TaskRow => ({
    id: `0198c36f-0000-7000-8000-0000000000c${n}`,
    workspace_id: WORKSPACE_ID,
    slug,
    base_model_id: BASE_MODEL_ID,
    comparison_model_id: comparison,
    trace_capture_rate: rate,
    production_model_id: null,
    production_changed_at: null,
    created_at: iso(-days(createdDaysAgo)),
    updated_at: iso(-days(1)),
  });
  const supportTriage = task("1", "support-triage", 0.55, 34, "gpt-4o");
  const sqlGeneration = task(
    "2",
    "sql-generation",
    1,
    6,
    "claude-3-5-sonnet-20241022",
  );
  const emailDraft = task("3", "email-draft", 1, 19, "gpt-4o-mini");
  const tasks = [supportTriage, sqlGeneration, emailDraft];

  const training_runs: TrainingRunRow[] = [];
  const run_logs: Record<string, TrainingRunEvent[]> = {};

  const addSucceeded = (
    t: TaskRow,
    runId: string,
    daysAgo: number,
    trigger: TrainingRunRow["trigger"],
    usable: number,
    strong: boolean,
    holdout?: number,
  ) => {
    const createdAt = new Date(Date.now() - days(daysAgo));
    const ds = datasetFor(runId, usable, daysAgo + 30, daysAgo, holdout);
    const modelId = versionIdFor(t.slug, createdAt);
    const summary = buildEvaluation({
      holdout: ds.holdout,
      comparison_model_id: t.comparison_model_id,
      judge: workspace.evaluation_judge,
      strong,
      at: iso(-days(daysAgo) + minutes(58)),
    });
    const run: TrainingRunRow = {
      id: runId,
      workspace_id: WORKSPACE_ID,
      task_id: t.id,
      trigger,
      base_model_id: t.base_model_id,
      stage: "succeeded",
      dataset: ds,
      evaluation: {
        judge: workspace.evaluation_judge,
        holdout: ds.holdout,
        summary,
      },
      provider_job_id: `training-${runId.slice(-6)}-1`,
      created_at: createdAt.toISOString(),
      updated_at: iso(-days(daysAgo) + minutes(60)),
    };
    training_runs.push(run);
    run_logs[runId] = fullRunLog(
      run,
      modelId,
      -days(daysAgo),
      minutes(9),
      ds,
      summary,
    );
    models.push({
      id: modelId,
      status: "available",
      trainable: false,
      workspace_id: WORKSPACE_ID,
      task_id: t.id,
      base_model_id: t.base_model_id,
      training_run_id: runId,
      adapter: adapterFor(modelId),
      created_at: iso(-days(daysAgo) + minutes(45)),
    });
    return modelId;
  };

  // support-triage: a failed manual attempt, two succeeded runs, one live run.
  const failedId = "0198c36f-0000-7000-8000-0000000000d0";
  const failedDs = datasetFor(failedId, 210, 60, 30);
  const failedRun: TrainingRunRow = {
    id: failedId,
    workspace_id: WORKSPACE_ID,
    task_id: supportTriage.id,
    trigger: "manual",
    base_model_id: BASE_MODEL_ID,
    stage: "failed",
    dataset: failedDs,
    evaluation: null,
    provider_job_id: null,
    created_at: iso(-days(30)),
    updated_at: iso(-days(30) + minutes(20)),
  };
  training_runs.push(failedRun);
  run_logs[failedId] = failedRunLog(failedRun, -days(30), minutes(8), failedDs);

  // The first version was promoted by hand; the second trained later and has not been.
  supportTriage.production_model_id = addSucceeded(
    supportTriage,
    "0198c36f-0000-7000-8000-0000000000d1",
    20,
    "manual",
    520,
    true,
  );
  supportTriage.production_changed_at = iso(-days(18));
  addSucceeded(
    supportTriage,
    "0198c36f-0000-7000-8000-0000000000d2",
    6,
    "automation",
    548,
    false,
    55,
  );
  const liveId = "0198c36f-0000-7000-8000-0000000000d3";
  training_runs.push({
    id: liveId,
    workspace_id: WORKSPACE_ID,
    task_id: supportTriage.id,
    trigger: "automation",
    base_model_id: BASE_MODEL_ID,
    stage: "queued",
    dataset: null,
    evaluation: null,
    provider_job_id: null,
    created_at: iso(-minutes(1)),
    updated_at: iso(-minutes(1)),
  });
  run_logs[liveId] = [
    event(1, iso(-minutes(1)), "control_plane", {
      type: "run_created",
      trigger: "automation",
      task_id: supportTriage.id,
      base_model_id: BASE_MODEL_ID,
    }),
    event(2, iso(-minutes(1) + 1000), "control_plane", {
      type: "stage_entered",
      stage: "queued",
    }),
  ];

  emailDraft.production_model_id = addSucceeded(
    emailDraft,
    "0198c36f-0000-7000-8000-0000000000e1",
    10,
    "manual",
    312,
    true,
    31,
  );
  emailDraft.production_changed_at = iso(-days(9));

  const st = buildTraces("support-triage", supportTriageTemplates, 18);
  const sq = buildTraces("sql-generation", sqlGenerationTemplates, 14);
  const ed = buildTraces("email-draft", emailDraftTemplates, 9);

  const stats: Record<string, TaskStats> = {
    [supportTriage.id]: {
      requests_7d: 9412,
      tokens_7d: 2_140_000,
      provider_spend_7d_nano_usd: Math.round(9.63 * NANO),
      traces_this_week: 412,
      usable_traces_since_last_run: 312,
    },
    [sqlGeneration.id]: {
      requests_7d: 641,
      tokens_7d: 386_000,
      provider_spend_7d_nano_usd: Math.round(2.91 * NANO),
      traces_this_week: 180,
      usable_traces_since_last_run: 180,
    },
    [emailDraft.id]: {
      requests_7d: 308,
      tokens_7d: 61_000,
      provider_spend_7d_nano_usd: Math.round(0.04 * NANO),
      traces_this_week: 96,
      usable_traces_since_last_run: 96,
    },
  };

  return {
    workspace,
    models,
    tasks,
    training_runs,
    run_logs,
    traces: [...st.rows, ...sq.rows, ...ed.rows],
    conversations: {
      ...st.conversations,
      ...sq.conversations,
      ...ed.conversations,
    },
    stats,
  };
};

// ---------------------------------------------------------------------------
// Derivations over the run log (run-log/service.ts: timeline, progress, failure)
// ---------------------------------------------------------------------------

export const runTimeline = (events: TrainingRunEvent[]): RunTimelineEntry[] =>
  events.flatMap((e) =>
    e.type === "stage_entered" ? [{ stage: e.stage, entered_at: e.at }] : [],
  );

export const runProgress = (events: TrainingRunEvent[]): RunProgress | null => {
  for (let i = events.length - 1; i >= 0; i--) {
    const e = events[i]!;
    if (e.type === "trainer_progress") {
      return {
        step: e.step,
        total_steps: e.total_steps,
        loss: e.loss,
        mean_reward: e.mean_reward,
        tokens_per_second: e.tokens_per_second,
        eta_seconds: e.eta_seconds,
      };
    }
  }
  return null;
};

export const runFailure = (
  events: TrainingRunEvent[],
): { error_code?: string; message?: string } | null => {
  for (let i = events.length - 1; i >= 0; i--) {
    const e = events[i]!;
    if (e.type === "run_finished" && e.stage !== "succeeded") {
      return {
        ...(e.error_code ? { error_code: e.error_code } : {}),
        ...(e.message ? { message: e.message } : {}),
      };
    }
    if (e.type === "trainer_failed")
      return { error_code: e.error_code, message: e.message };
  }
  return null;
};

/**
 * Slice the log per stage for the step list. Events carry no stage: a control-plane event
 * belongs to the most recent `stage_entered` before it; trainer events always belong to
 * `training` (their merge can lag the control plane's own transitions).
 */
export const runLogByStage = (
  events: TrainingRunEvent[],
): Partial<Record<RunStage, TrainingRunEvent[]>> => {
  const out: Partial<Record<RunStage, TrainingRunEvent[]>> = {};
  let current: RunStage = "queued";
  for (const e of events) {
    if (e.type === "stage_entered") current = e.stage;
    const bucket: RunStage = e.source === "trainer" ? "training" : current;
    (out[bucket] ??= []).push(e);
  }
  return out;
};

/** Render one event as the line the console shows in a step's log pane. */
export const describeEvent = (e: TrainingRunEvent): string => {
  switch (e.type) {
    case "run_created":
      return `run created (${e.trigger}) on ${e.base_model_id}`;
    case "stage_entered":
      return `→ ${e.stage}`;
    case "dataset_built":
      return `dataset: ${e.usable} eligible, ${e.deduplicated} after dedupe, train ${e.train} / validation ${e.validation} / holdout ${e.holdout} (${e.oldest_trace_at.slice(0, 10)} → ${e.newest_trace_at.slice(0, 10)})`;
    case "capacity_granted":
      return `host ${e.host_id} granted (${e.gpu.count}× ${e.gpu.type})`;
    case "job_submitted":
      return `job ${e.provider_job_id} registered on ${e.host_id} via ${e.runner}`;
    case "job_status":
      return `job ${e.state}${e.message ? `: ${e.message}` : ""}`;
    case "model_reserved":
      return `model id reserved: ${e.model_id}`;
    case "artifact_verified":
      return `artifact verified: ${(e.size_bytes / 1_048_576).toFixed(1)} MB sha256=${e.sha256.slice(0, 8)}… loads and matches reference outputs`;
    case "adapter_loaded":
      return `loaded on ${e.host_id}`;
    case "evaluation_progress":
      return `evaluation ${e.completed}/${e.total}`;
    case "evaluation_completed":
      return `evaluation over ${e.groups} sessions: win ${Math.round(e.win * 100)}% · tie ${Math.round(e.tie * 100)}% · loss ${Math.round(e.loss * 100)}% · unresolved ${Math.round(e.unresolved * 100)}% (judge ${e.judge})`;
    case "published":
      return `published ${e.model_id}; callable by exact id`;
    case "cancel_requested":
      return `cancel requested by ${e.requested_by}`;
    case "run_finished":
      return `run ${e.stage}${e.error_code ? ` (${e.error_code})` : ""}${e.message ? `: ${e.message}` : ""}`;
    case "note":
      return `${e.level}: ${e.message}`;
    case "trainer_started":
      return `trainer started on ${e.gpu} · recipe ${e.recipe} · image ${e.image_digest}`;
    case "trainer_stage":
      return `trainer: ${e.stage}`;
    case "trainer_progress":
      return `step ${e.step}/${e.total_steps} reward=${e.mean_reward.toFixed(3)} loss=${e.loss.toFixed(3)} tok/s=${e.tokens_per_second} eta=${e.eta_seconds}s`;
    case "trainer_checkpoint":
      return `checkpoint at step ${e.step} sha256=${e.sha256.slice(0, 8)}…`;
    case "trainer_artifact_uploaded":
      return `uploaded ${e.name} (${(e.size_bytes / 1_048_576).toFixed(1)} MB) sha256=${e.sha256.slice(0, 8)}…`;
    case "trainer_finished":
      return `trainer finished, manifest ${e.manifest_sha256.slice(0, 8)}…`;
    case "trainer_failed":
      return `trainer failed (${e.error_code}): ${e.message}`;
  }
};

// ---------------------------------------------------------------------------
// Live run stage machine (appends events exactly as the orchestrator would)
// ---------------------------------------------------------------------------

const advanceLiveRun = (
  run: TrainingRunRow,
  log: TrainingRunEvent[],
  task: TaskRow,
  judge: EvaluationJudge,
  existingIds: string[],
): { run: TrainingRunRow; log: TrainingRunEvent[]; newModel?: ModelRow } => {
  let seq = log.length ? log[log.length - 1]!.seq : 0;
  const now = iso(0);
  const cp = (p: TrainingRunEventPayload) =>
    event(++seq, now, "control_plane", p);
  const tr = (p: TrainingRunEventPayload) => event(++seq, now, "trainer", p);
  const enter = (stage: RunStage) => cp({ type: "stage_entered", stage });
  const next: TrainingRunRow = { ...run, updated_at: now };
  const events: TrainingRunEvent[] = [];
  const reservedId = () => {
    const found = log.find((e) => e.type === "model_reserved");
    return found && found.type === "model_reserved" ? found.model_id : null;
  };
  const gpu = { type: "NVIDIA H200", count: 8 };

  switch (run.stage) {
    case "cancelling":
      next.stage = "cancelled";
      events.push(
        enter("cancelled"),
        cp({ type: "run_finished", stage: "cancelled" }),
      );
      break;
    case "queued":
      next.stage = "building_dataset";
      events.push(enter("building_dataset"));
      break;
    case "building_dataset": {
      const ds = datasetFor(
        run.id,
        520 + Math.round(Math.random() * 60),
        30,
        0,
      );
      next.dataset = ds;
      next.stage = "awaiting_capacity";
      events.push(cp(datasetBuilt(ds)), enter("awaiting_capacity"));
      break;
    }
    case "awaiting_capacity": {
      const base = versionIdFor(task.slug, new Date());
      const clashes = existingIds.filter(
        (id) => id === base || id.startsWith(`${base}-`),
      ).length;
      const modelId = clashes ? `${base}-${clashes + 1}` : base;
      next.stage = "training";
      next.provider_job_id = `training-${run.id.slice(-6)}-1`;
      events.push(
        cp({ type: "capacity_granted", host_id: HOSTS[0]!, gpu }),
        enter("training"),
        cp({ type: "model_reserved", model_id: modelId }),
        cp({
          type: "job_submitted",
          runner: "nomad",
          provider_job_id: next.provider_job_id,
          host_id: HOSTS[0]!,
          gpu,
        }),
        tr({
          type: "trainer_started",
          gpu: "8× NVIDIA H200 141GB",
          image_digest: TRAINER_IMAGE,
          recipe: RECIPE,
        }),
        tr({ type: "trainer_stage", stage: "training" }),
        tr({
          type: "trainer_progress",
          step: 0,
          total_steps: TOTAL_STEPS,
          loss: 0.9,
          mean_reward: 0.41,
          tokens_per_second: 1312,
          eta_seconds: 620,
        }),
      );
      break;
    }
    case "training": {
      const p = runProgress(log) ?? {
        step: 0,
        total_steps: TOTAL_STEPS,
        loss: 0.9,
        mean_reward: 0.41,
        tokens_per_second: 1312,
        eta_seconds: 620,
      };
      const step = Math.min(
        p.total_steps,
        p.step + Math.round(p.total_steps * 0.22),
      );
      events.push(
        tr({
          type: "trainer_progress",
          step,
          total_steps: p.total_steps,
          loss: Math.max(0.16, Number((p.loss * 0.82).toFixed(3))),
          mean_reward: Math.min(
            0.86,
            Number((p.mean_reward + 0.09).toFixed(3)),
          ),
          tokens_per_second: 1312,
          eta_seconds: Math.max(0, Math.round(p.eta_seconds * 0.55)),
        }),
      );
      if (step >= p.total_steps) {
        next.stage = "verifying";
        events.push(
          tr({ type: "trainer_stage", stage: "uploading" }),
          tr({
            type: "trainer_finished",
            manifest_sha256: sha(`${run.id}-manifest`),
          }),
          cp({ type: "job_status", state: "complete" }),
          enter("verifying"),
        );
      }
      break;
    }
    case "verifying": {
      const modelId = reservedId() ?? versionIdFor(task.slug, new Date());
      next.stage = "publishing";
      events.push(
        cp({
          type: "artifact_verified",
          model_id: modelId,
          sha256: sha(`${run.id}-adapter`),
          size_bytes: 231_735_296,
        }),
        enter("publishing"),
      );
      break;
    }
    case "publishing": {
      const modelId = reservedId() ?? versionIdFor(task.slug, new Date());
      const ds = run.dataset!;
      next.stage = "evaluating";
      next.evaluation = {
        judge,
        holdout: ds.holdout,
        summary: buildEvaluation({
          holdout: ds.holdout,
          comparison_model_id: task.comparison_model_id,
          judge,
          strong: true,
          at: now,
        }),
      };
      events.push(
        cp({ type: "adapter_loaded", host_id: HOSTS[0]! }),
        cp({ type: "adapter_loaded", host_id: HOSTS[1]! }),
        cp({ type: "published", model_id: modelId }),
        enter("evaluating"),
      );
      // Publication makes the version callable by its exact id before evaluation (SERV-02).
      return {
        run: next,
        log: [...log, ...events],
        newModel: {
          id: modelId,
          status: "available",
          trainable: false,
          workspace_id: run.workspace_id,
          task_id: run.task_id,
          base_model_id: run.base_model_id,
          training_run_id: run.id,
          adapter: adapterFor(modelId),
          created_at: now,
        },
      };
    }
    case "evaluating": {
      const s = run.evaluation!.summary;
      next.stage = "succeeded";
      events.push(
        cp({
          type: "evaluation_completed",
          judge: s.judge_model_id,
          groups: s.holdout_groups,
          win: s.vs_comparison.win,
          tie: s.vs_comparison.tie,
          loss: s.vs_comparison.loss,
          unresolved: s.vs_comparison.unresolved,
        }),
        enter("succeeded"),
        cp({ type: "run_finished", stage: "succeeded" }),
      );
      break;
    }
    default:
      return { run, log };
  }
  return { run: next, log: [...log, ...events] };
};

// ---------------------------------------------------------------------------
// Store
// ---------------------------------------------------------------------------

interface FineTuningStore extends Seed {
  connect_api_key: string | null;
  connect_task_slug: string;
  connection_status: "waiting" | "connected";

  /** PUT P/trace-capture */
  setTraceCapture: (enabled: boolean) => void;
  /** PUT P/evaluation-judge */
  setEvaluationJudge: (judge: EvaluationJudge) => void;
  /** PATCH P/tasks/{task_id} { base_model_id } */
  setTaskBaseModel: (taskId: string, baseModelId: string) => void;
  /** PATCH P/tasks/{task_id} { comparison_model_id } — applies to future runs only */
  setTaskComparisonModel: (taskId: string, modelId: string) => void;
  /** POST P/tasks/{task_id}/promotions — the task name resolves to this version from now on (SERV-03) */
  promote: (taskId: string, modelId: string) => void;
  createApiKey: () => void;
  setConnectTaskSlug: (slug: string) => void;
  markConnected: () => void;
  /** POST P/tasks/{task_id}/runs → 201 (409 while a run is active; the button is disabled then) */
  createRun: (taskId: string) => void;
  /** POST .../runs/{run_id}/cancel → guarded move to `cancelling`; the orchestrator finishes it */
  cancelRun: (runId: string) => void;
  tickActiveRuns: () => void;
}

export const useMockFineTuning = create<FineTuningStore>()((set, get) => ({
  ...seed(),
  connect_api_key: null,
  connect_task_slug: "support-triage",
  connection_status: "waiting",

  setTraceCapture: (enabled) =>
    set((s) => ({
      workspace: { ...s.workspace, trace_capture_enabled: enabled },
    })),
  setEvaluationJudge: (judge) =>
    set((s) => ({ workspace: { ...s.workspace, evaluation_judge: judge } })),
  setTaskBaseModel: (taskId, baseModelId) =>
    set((s) => ({
      tasks: s.tasks.map((t) =>
        t.id === taskId
          ? { ...t, base_model_id: baseModelId, updated_at: iso(0) }
          : t,
      ),
    })),
  setTaskComparisonModel: (taskId, modelId) =>
    set((s) => ({
      tasks: s.tasks.map((t) =>
        t.id === taskId
          ? { ...t, comparison_model_id: modelId, updated_at: iso(0) }
          : t,
      ),
    })),
  promote: (taskId, modelId) =>
    set((s) => ({
      tasks: s.tasks.map((t) =>
        t.id === taskId &&
        s.models.some((m) => m.id === modelId && m.task_id === taskId)
          ? {
              ...t,
              production_model_id: modelId,
              production_changed_at: iso(0),
              updated_at: iso(0),
            }
          : t,
      ),
    })),
  createApiKey: () =>
    set({
      connect_api_key: `grad_${Array.from({ length: 24 }, () => "abcdefghijklmnopqrstuvwxyz0123456789"[Math.floor(Math.random() * 36)]).join("")}`,
    }),
  setConnectTaskSlug: (slug) => set({ connect_task_slug: slug }),
  markConnected: () => set({ connection_status: "connected" }),

  createRun: (taskId) => {
    const { tasks, training_runs, run_logs, workspace } = get();
    const task = tasks.find((t) => t.id === taskId);
    if (
      !task ||
      training_runs.some(
        (r) => r.task_id === taskId && !TERMINAL_STAGES.includes(r.stage),
      )
    )
      return;
    const id = `0198c36f-0000-7000-8000-${Date.now().toString(16).padStart(12, "0")}`;
    const now = iso(0);
    const run: TrainingRunRow = {
      id,
      workspace_id: workspace.id,
      task_id: taskId,
      trigger: "manual",
      base_model_id: task.base_model_id,
      stage: "queued",
      dataset: null,
      evaluation: null,
      provider_job_id: null,
      created_at: now,
      updated_at: now,
    };
    set({
      training_runs: [run, ...training_runs],
      run_logs: {
        ...run_logs,
        [id]: [
          event(1, now, "control_plane", {
            type: "run_created",
            trigger: "manual",
            task_id: taskId,
            base_model_id: task.base_model_id,
            requested_by: "josh@gradiated.com",
          }),
          event(2, now, "control_plane", {
            type: "stage_entered",
            stage: "queued",
          }),
        ],
      },
    });
  },

  cancelRun: (runId) =>
    set((s) => {
      const run = s.training_runs.find((r) => r.id === runId);
      if (
        !run ||
        TERMINAL_STAGES.includes(run.stage) ||
        run.stage === "cancelling"
      )
        return {};
      const log = s.run_logs[runId] ?? [];
      const seq = log.length ? log[log.length - 1]!.seq : 0;
      const now = iso(0);
      return {
        training_runs: s.training_runs.map((r) =>
          r.id === runId
            ? { ...r, stage: "cancelling" as const, updated_at: now }
            : r,
        ),
        run_logs: {
          ...s.run_logs,
          [runId]: [
            ...log,
            event(seq + 1, now, "control_plane", {
              type: "cancel_requested",
              requested_by: "josh@gradiated.com",
            }),
            event(seq + 2, now, "control_plane", {
              type: "stage_entered",
              stage: "cancelling",
            }),
          ],
        },
      };
    }),

  tickActiveRuns: () => {
    const s = get();
    let changed = false;
    const newModels: ModelRow[] = [];
    const finishedTasks = new Set<string>();
    const run_logs = { ...s.run_logs };
    const training_runs = s.training_runs.map((run) => {
      if (TERMINAL_STAGES.includes(run.stage)) return run;
      const task = s.tasks.find((t) => t.id === run.task_id);
      if (!task) return run;
      const result = advanceLiveRun(
        run,
        run_logs[run.id] ?? [],
        task,
        s.workspace.evaluation_judge,
        s.models.map((m) => m.id),
      );
      if (result.run === run) return run;
      changed = true;
      run_logs[run.id] = result.log;
      if (result.newModel) newModels.push(result.newModel);
      if (result.run.stage === "succeeded") finishedTasks.add(task.id);
      return result.run;
    });
    if (!changed) return;
    set({
      training_runs,
      run_logs,
      models: newModels.length ? [...s.models, ...newModels] : s.models,
      stats: finishedTasks.size
        ? Object.fromEntries(
            Object.entries(s.stats).map(([id, st]) => [
              id,
              finishedTasks.has(id)
                ? { ...st, usable_traces_since_last_run: 0 }
                : st,
            ]),
          )
        : s.stats,
    });
  },
}));

if (typeof window !== "undefined") {
  window.setInterval(() => useMockFineTuning.getState().tickActiveRuns(), 3200);
}

// ---------------------------------------------------------------------------
// Selectors (what the API routes would return)
// ---------------------------------------------------------------------------

export const versionsForTask = (
  s: Pick<Seed, "models" | "training_runs" | "workspace" | "tasks">,
  taskId: string,
): VersionView[] => {
  const task = s.tasks.find((t) => t.id === taskId);
  const production = s.models.find((m) => m.id === task?.production_model_id);
  return s.models
    .filter((m) => m.task_id === taskId && m.training_run_id)
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
    .flatMap((model) => {
      const run = s.training_runs.find((r) => r.id === model.training_run_id);
      if (!run?.evaluation) return [];
      return [
        {
          model,
          run,
          summary: run.evaluation.summary,
          workspace_name: s.workspace.name,
          is_production: production?.id === model.id,
          newer_than_production: Boolean(
            production && model.created_at > production.created_at,
          ),
        },
      ];
    });
};

/** GET P/traces — grouped by trace_id, newest first. */
export const traceSummaries = (
  rows: TraceGenerationRow[],
  taskSlug: string,
): TraceSummary[] => {
  const byTrace = new Map<string, TraceGenerationRow[]>();
  for (const r of rows) {
    if (r.task !== taskSlug) continue;
    const list = byTrace.get(r.trace_id);
    if (list) list.push(r);
    else byTrace.set(r.trace_id, [r]);
  }
  return [...byTrace.entries()]
    .map(([trace_id, gens]) => {
      const sorted = [...gens].sort((a, b) =>
        a.captured_at.localeCompare(b.captured_at),
      );
      const first = sorted[0]!;
      const last = sorted[sorted.length - 1]!;
      return {
        trace_id,
        started_at: first.captured_at,
        generation_count: sorted.length,
        duration_ms:
          new Date(last.captured_at).getTime() -
          new Date(first.captured_at).getTime() +
          last.latency_ms,
        cost_nano_usd: sorted.reduce((a, g) => a + g.cost_nano_usd, 0),
        single_generation: sorted.length === 1 && trace_id === first.id,
      };
    })
    .sort((a, b) => b.started_at.localeCompare(a.started_at));
};

/** GET .../runs/{run_id}/evaluation-results — mocked from the task's traces, stable per model. */
export const evaluationResults = (
  version: VersionView,
  conversations: Record<string, TraceMessage[]>,
  rows: TraceGenerationRow[],
  taskSlug: string,
  limit = 12,
): EvaluationResultLine[] => {
  const traceIds = [
    ...new Set(rows.filter((r) => r.task === taskSlug).map((r) => r.trace_id)),
  ];
  let seedNum = 0;
  for (const ch of version.model.id)
    seedNum = (seedNum * 31 + ch.charCodeAt(0)) >>> 0;
  const next = () => {
    seedNum = (seedNum * 1103515245 + 12345) >>> 0;
    return (seedNum >>> 8) / 16777216;
  };
  const { win, tie, loss } = version.summary.vs_comparison;
  return Array.from(
    { length: Math.min(limit, version.summary.holdout_examples) },
    (_, i) => {
      const conv =
        conversations[traceIds[i % Math.max(1, traceIds.length)] ?? ""] ?? [];
      const user = conv.find((m) => m.role === "user")?.content ?? "";
      const turn = conv.find((m) => m.role === "assistant");
      const canonical = turn?.tool_call
        ? `${turn.tool_call.name}(${turn.tool_call.arguments})`
        : (turn?.content ?? "");
      const degraded = turn?.tool_call
        ? `${turn.tool_call.name}(${turn.tool_call.arguments.replace(/"priority":"[a-z]+"/, '"priority":"low"')})`
        : `${canonical.split(". ")[0]}.`;
      const r = next();
      const verdict: EvaluationResultLine["verdict"] =
        r < win
          ? "better"
          : r < win + tie
            ? "equivalent"
            : r < win + tie + loss
              ? "worse"
              : "unresolved";
      return {
        index: i + 1,
        request_preview: user,
        comparison_response: verdict === "better" ? degraded : canonical,
        fine_tuned_response: verdict === "worse" ? degraded : canonical,
        verdict,
      };
    },
  );
};
