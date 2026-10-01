import type {
  Gpu,
  RunProgress,
  RunStage,
  TrainingRunEvent,
} from "@/store/fine-tuning-types";

export const MEBIBYTE = 1_048_576;

export const runTimeline = (
  events: readonly TrainingRunEvent[],
): { stage: RunStage; entered_at: string }[] =>
  events.flatMap((event) =>
    event.payload.type === "stage_entered"
      ? [{ stage: event.payload.stage, entered_at: event.at }]
      : [],
  );

export const runProgress = (
  events: readonly TrainingRunEvent[],
): RunProgress | null => {
  const latest = events.findLast(
    (event) => event.payload.type === "trainer_progress",
  );
  if (latest?.payload.type !== "trainer_progress") return null;

  const { type: _type, ...progress } = latest.payload;

  return progress;
};

export const runLogByStage = (
  events: readonly TrainingRunEvent[],
): Partial<Record<RunStage, TrainingRunEvent[]>> => {
  const byStage: Partial<Record<RunStage, TrainingRunEvent[]>> = {};
  let current: RunStage = "queued";

  for (const event of events) {
    if (event.payload.type === "stage_entered") current = event.payload.stage;

    // Training progress can arrive after the workflow has entered a later stage.
    const bucket = event.payload.type.startsWith("trainer_")
      ? "training"
      : event.payload.type === "evaluation_progress" ||
          event.payload.type === "evaluation_completed"
        ? "evaluating"
        : current;
    (byStage[bucket] ??= []).push(event);
  }

  return byStage;
};

const megabytes = (bytes: number) => (bytes / MEBIBYTE).toFixed(1);

const shortDigest = (sha256: string) => `${sha256.slice(0, 8)}…`;

const gpuLabel = ({ count, type }: Gpu) => `${count}× ${type}`;

const formatMetrics = (metrics: Record<string, number> | undefined) =>
  Object.entries(metrics ?? {})
    .map(([name, value]) => ` ${name}=${value}`)
    .join("");

const percent = (fraction: number) => Math.round(fraction * 100);

export const describeEvent = ({ payload: event }: TrainingRunEvent): string => {
  switch (event.type) {
    case "run_created":
      return `run created (${event.trigger}) on ${event.base_model_id}`;
    case "stage_entered":
      return event.stage.replaceAll("_", " ");
    case "dataset_built":
      return `dataset: ${event.eligible_examples} eligible, ${event.duplicates_removed} duplicates removed, train ${event.train} / validation ${event.validation} / test ${event.test}${event.evaluation_examples === undefined ? "" : ` / evaluation sample ${event.evaluation_examples}`}${event.oldest_trace_at && event.newest_trace_at ? ` (${event.oldest_trace_at.slice(0, 10)} to ${event.newest_trace_at.slice(0, 10)})` : ""}`;
    case "capacity_granted":
      return `host ${event.host_id} granted (${gpuLabel(event.gpu)})`;
    case "job_submitted":
      return `job ${event.provider_job_id} registered on ${event.host_id} via ${event.runner}`;
    case "job_status":
      return `job ${event.state}${event.message ? `: ${event.message}` : ""}`;
    case "artifact_verified":
      return `artifact verified: ${megabytes(event.size_bytes)} MB sha256=${shortDigest(event.sha256)} loads and matches reference outputs`;
    case "adapter_loaded":
      return `loaded on ${event.host_id}`;
    case "evaluation_progress":
      return `evaluation ${event.completed}/${event.total}`;
    case "evaluation_completed":
      return `evaluation over ${event.groups} groups: win ${percent(event.win)}% · tie ${percent(event.tie)}% · loss ${percent(event.loss)}% · unresolved ${percent(event.unresolved)}% (judge ${event.judge})`;
    case "published":
      return `published ${event.name}`;
    case "cancel_requested":
      return `cancel requested by ${event.requested_by}`;
    case "run_finished":
      return `run ${event.stage}${event.error_code ? ` (${event.error_code})` : ""}${event.message ? `: ${event.message}` : ""}`;
    case "note":
      return `${event.level}: ${event.message}`;
    case "trainer_progress":
      return `step ${event.step}${event.total_steps === undefined ? "" : `/${event.total_steps}`}${event.train_loss === undefined ? "" : ` loss=${event.train_loss.toFixed(3)}`}${event.tokens_per_second === undefined ? "" : ` tok/s=${event.tokens_per_second}`}${event.eta_seconds === undefined ? "" : ` eta=${event.eta_seconds}s`}${formatMetrics(event.metrics)}`;
    case "trainer_observation":
      return `${event.level ? `${event.level}: ` : ""}${event.message}${event.step === undefined ? "" : ` (step ${event.step})`}${formatMetrics(event.metrics)}${event.details ? ` ${JSON.stringify(event.details)}` : ""}`;
    case "trainer_checkpoint":
      return `checkpoint at step ${event.step} sha256=${shortDigest(event.sha256)}`;
  }
};
