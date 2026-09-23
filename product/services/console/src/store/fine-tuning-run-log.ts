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
    event.type === "stage_entered"
      ? [{ stage: event.stage, entered_at: event.at }]
      : [],
  );

export const runProgress = (
  events: readonly TrainingRunEvent[],
): RunProgress | null => {
  const latest = events.findLast((event) => event.type === "trainer_progress");
  if (latest?.type !== "trainer_progress") return null;

  const {
    step,
    total_steps,
    loss,
    mean_reward,
    tokens_per_second,
    eta_seconds,
  } = latest;

  return {
    step,
    total_steps,
    loss,
    mean_reward,
    tokens_per_second,
    eta_seconds,
  };
};

export const runLogByStage = (
  events: readonly TrainingRunEvent[],
): Partial<Record<RunStage, TrainingRunEvent[]>> => {
  const byStage: Partial<Record<RunStage, TrainingRunEvent[]>> = {};
  let current: RunStage = "queued";

  for (const event of events) {
    if (event.type === "stage_entered") current = event.stage;

    // Trainer events always go in `training`: their merge can lag the control plane's transitions.
    const bucket = event.source === "trainer" ? "training" : current;
    (byStage[bucket] ??= []).push(event);
  }

  return byStage;
};

const megabytes = (bytes: number) => (bytes / MEBIBYTE).toFixed(1);

const shortDigest = (sha256: string) => `${sha256.slice(0, 8)}…`;

const gpuLabel = ({ count, type }: Gpu) => `${count}× ${type}`;

const percent = (fraction: number) => Math.round(fraction * 100);

export const describeEvent = (event: TrainingRunEvent): string => {
  switch (event.type) {
    case "run_created":
      return `run created (${event.trigger}) on ${event.base_model_id}`;
    case "stage_entered":
      return `→ ${event.stage}`;
    case "dataset_built":
      return `dataset: ${event.usable} eligible, ${event.deduplicated} after dedupe, train ${event.train} / validation ${event.validation} / holdout ${event.holdout} (${event.oldest_trace_at.slice(0, 10)} → ${event.newest_trace_at.slice(0, 10)})`;
    case "capacity_granted":
      return `host ${event.host_id} granted (${gpuLabel(event.gpu)})`;
    case "job_submitted":
      return `job ${event.provider_job_id} registered on ${event.host_id} via ${event.runner}`;
    case "job_status":
      return `job ${event.state}${event.message ? `: ${event.message}` : ""}`;
    case "model_reserved":
      return `model id reserved: ${event.model_id}`;
    case "artifact_verified":
      return `artifact verified: ${megabytes(event.size_bytes)} MB sha256=${shortDigest(event.sha256)} loads and matches reference outputs`;
    case "adapter_loaded":
      return `loaded on ${event.host_id}`;
    case "evaluation_progress":
      return `evaluation ${event.completed}/${event.total}`;
    case "evaluation_completed":
      return `evaluation over ${event.groups} sessions: win ${percent(event.win)}% · tie ${percent(event.tie)}% · loss ${percent(event.loss)}% · unresolved ${percent(event.unresolved)}% (judge ${event.judge})`;
    case "published":
      return `published ${event.model_id}; callable by exact id`;
    case "cancel_requested":
      return `cancel requested by ${event.requested_by}`;
    case "run_finished":
      return `run ${event.stage}${event.error_code ? ` (${event.error_code})` : ""}${event.message ? `: ${event.message}` : ""}`;
    case "note":
      return `${event.level}: ${event.message}`;
    case "trainer_started":
      return `trainer started on ${gpuLabel(event.gpu)} · recipe ${event.recipe} · image ${event.image_digest}`;
    case "trainer_stage":
      return `trainer: ${event.stage}`;
    case "trainer_progress":
      return `step ${event.step}/${event.total_steps} reward=${event.mean_reward.toFixed(3)} loss=${event.loss.toFixed(3)} tok/s=${event.tokens_per_second} eta=${event.eta_seconds}s`;
    case "trainer_checkpoint":
      return `checkpoint at step ${event.step} sha256=${shortDigest(event.sha256)}`;
    case "trainer_artifact_uploaded":
      return `uploaded ${event.name} (${megabytes(event.size_bytes)} MB) sha256=${shortDigest(event.sha256)}`;
    case "trainer_finished":
      return `trainer finished, manifest ${shortDigest(event.manifest_sha256)}`;
    case "trainer_failed":
      return `trainer failed (${event.error_code}): ${event.message}`;
  }
};
