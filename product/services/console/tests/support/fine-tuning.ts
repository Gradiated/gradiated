import type {
  TaskRow,
  TraceGenerationRow,
  TrainingRunEvent,
  TrainingRunEventPayload,
} from "@/store/fine-tuning-types";
import { versionsForTask } from "@/store/fine-tuning-views";
import { useMockFineTuning } from "@/store/mock-fine-tuning";

export const runEvent = (
  seq: number,
  source: TrainingRunEvent["source"],
  payload: TrainingRunEventPayload,
): TrainingRunEvent => ({
  schema_version: 1,
  attempt: 1,
  seq,
  at: new Date(Date.UTC(2026, 8, 1, 0, 0, seq)).toISOString(),
  source,
  ...payload,
});

export const traceRow = (
  overrides: Partial<TraceGenerationRow> &
    Pick<TraceGenerationRow, "id" | "trace_id" | "captured_at">,
): TraceGenerationRow => ({
  task: "support-triage",
  response_status: 200,
  model: "gpt-4o",
  latency_ms: 100,
  input_tokens: 10,
  output_tokens: 20,
  cost_nano_usd: 1_000,
  ...overrides,
});

export const defined = <T>(value: T | undefined): T => {
  if (value === undefined) throw new Error("Seed is missing an expected row");

  return value;
};

export const findTask = (tasks: readonly TaskRow[], slug: string): TaskRow => {
  const task = tasks.find((candidate) => candidate.slug === slug);
  if (!task) throw new Error(`Seed has no ${slug} task`);

  return task;
};

export const seededSupportTriage = () => {
  const seed = useMockFineTuning.getInitialState();
  const task = findTask(seed.tasks, "support-triage");
  const version = defined(versionsForTask(seed, task.id)[0]);

  return { seed, task, version };
};
