import type {
  ModelRow,
  TaskRow,
  TaskStats,
  TraceGenerationRow,
  TraceMessage,
  TrainingRunEvent,
  TrainingRunRow,
  WorkspaceRow,
} from "@/store/fine-tuning-types";
import { seedTraces } from "@/store/mock-traces";
import {
  newRun,
  replayFailedRun,
  replaySucceededRun,
} from "@/store/mock-training-runs";
import {
  BASE_MODEL_ID,
  DAY_MS,
  MINUTE_MS,
  WORKSPACE_ID,
  isoAt,
} from "@/store/mock-values";

const catalogModel = (
  id: string,
  trainable: boolean,
  createdAt: number,
): ModelRow => ({
  id,
  status: "available",
  trainable,
  workspace_id: null,
  task_id: null,
  base_model_id: null,
  training_run_id: null,
  adapter: null,
  created_at: isoAt(createdAt),
});

const task = (
  id: string,
  slug: string,
  comparisonModelId: string,
): TaskRow => ({
  id,
  slug,
  base_model_id: BASE_MODEL_ID,
  comparison_model_id: comparisonModelId,
  production_model_id: null,
});

export interface FineTuningSeed {
  workspace: WorkspaceRow;
  models: ModelRow[];
  tasks: TaskRow[];
  training_runs: TrainingRunRow[];
  run_logs: Record<string, TrainingRunEvent[]>;
  traces: TraceGenerationRow[];
  conversations: Record<string, TraceMessage[]>;
  stats: Record<string, TaskStats>;
}

export const seedFineTuning = (now: number): FineTuningSeed => {
  const workspace: WorkspaceRow = {
    id: WORKSPACE_ID,
    trace_capture_enabled: true,
    evaluation_judge: "openai/gpt-5.6-sol",
  };
  const supportTriage = task(
    "0198c36f-0000-7000-8000-0000000000c1",
    "support-triage",
    "gpt-4o",
  );
  const sqlGeneration = task(
    "0198c36f-0000-7000-8000-0000000000c2",
    "sql-generation",
    "claude-3-5-sonnet-20241022",
  );
  const emailDraft = task(
    "0198c36f-0000-7000-8000-0000000000c3",
    "email-draft",
    "gpt-4o-mini",
  );

  const models: ModelRow[] = [
    catalogModel(BASE_MODEL_ID, true, now - 120 * DAY_MS),
    catalogModel("z-ai/glm-5.3-flash", false, now - 90 * DAY_MS),
  ];
  const failed = replayFailedRun(
    supportTriage,
    "0198c36f-0000-7000-8000-0000000000d0",
    now - 30 * DAY_MS,
  );
  const training_runs = [failed.run];
  const run_logs: Record<string, TrainingRunEvent[]> = {
    [failed.run.id]: failed.log,
  };

  const replay = (
    target: TaskRow,
    trigger: TrainingRunRow["trigger"],
    runId: string,
    daysAgo: number,
  ) => {
    const result = replaySucceededRun({
      task: target,
      trigger,
      runId,
      startedAt: now - daysAgo * DAY_MS,
      judge: workspace.evaluation_judge,
      existingIds: models.map((model) => model.id),
    });

    training_runs.push(result.run);
    run_logs[result.run.id] = result.log;
    if (result.published) models.push(result.published);

    return result.published?.id ?? null;
  };

  const supportProduction = replay(
    supportTriage,
    "manual",
    "0198c36f-0000-7000-8000-0000000000d1",
    20,
  );
  replay(
    supportTriage,
    "automation",
    "0198c36f-0000-7000-8000-0000000000d2",
    6,
  );
  const emailProduction = replay(
    emailDraft,
    "manual",
    "0198c36f-0000-7000-8000-0000000000e1",
    10,
  );

  const live = newRun(
    supportTriage,
    "automation",
    "0198c36f-0000-7000-8000-0000000000d3",
    isoAt(now - MINUTE_MS),
  );
  training_runs.push(live.run);
  run_logs[live.run.id] = live.log;

  return {
    workspace,
    models,
    tasks: [
      { ...supportTriage, production_model_id: supportProduction },
      sqlGeneration,
      { ...emailDraft, production_model_id: emailProduction },
    ],
    training_runs,
    run_logs,
    ...seedTraces(now),
    stats: {
      [supportTriage.id]: {
        requests_7d: 9412,
        tokens_7d: 2_140_000,
        usable_traces_since_last_run: 312,
      },
      [sqlGeneration.id]: {
        requests_7d: 641,
        tokens_7d: 386_000,
        usable_traces_since_last_run: 180,
      },
      [emailDraft.id]: {
        requests_7d: 308,
        tokens_7d: 61_000,
        usable_traces_since_last_run: 96,
      },
    },
  };
};
