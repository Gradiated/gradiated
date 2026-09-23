import {
  isFineTuned,
  type ModelRow,
  type TaskRow,
  type TraceGenerationRow,
  type TraceSummary,
  type TrainingRunRow,
  type VersionView,
} from "@/store/fine-tuning-types";

type VersionSource = Readonly<{
  models: readonly ModelRow[];
  training_runs: readonly TrainingRunRow[];
  tasks: readonly TaskRow[];
}>;

export const versionsForTask = (
  state: VersionSource,
  taskId: string,
): VersionView[] => {
  const productionId = state.tasks.find(
    (candidate) => candidate.id === taskId,
  )?.production_model_id;

  return state.models
    .filter(isFineTuned)
    .filter((model) => model.task_id === taskId)
    .toSorted((a, b) => b.created_at.localeCompare(a.created_at))
    .flatMap((model) => {
      const run = state.training_runs.find(
        (candidate) => candidate.id === model.training_run_id,
      );
      if (!run?.evaluation) return [];

      return [
        {
          model,
          run,
          summary: run.evaluation,
          is_production: model.id === productionId,
        },
      ];
    });
};

export const currentVersion = (
  versions: readonly VersionView[],
): VersionView | undefined =>
  versions.find((version) => version.is_production) ?? versions[0];

export const traceSummaries = (
  rows: readonly TraceGenerationRow[],
  taskSlug: string,
): TraceSummary[] => {
  const byTrace = new Map<string, TraceGenerationRow[]>();
  for (const row of rows) {
    if (row.task !== taskSlug) continue;

    byTrace.set(row.trace_id, [...(byTrace.get(row.trace_id) ?? []), row]);
  }

  return [...byTrace]
    .flatMap(([trace_id, generations]) => {
      const sorted = generations.toSorted((a, b) =>
        a.captured_at.localeCompare(b.captured_at),
      );
      const first = sorted[0];
      const last = sorted.at(-1);
      if (!first || !last) return [];

      return [
        {
          trace_id,
          started_at: first.captured_at,
          generation_count: sorted.length,
          duration_ms:
            Date.parse(last.captured_at) -
            Date.parse(first.captured_at) +
            last.latency_ms,
          cost_nano_usd: sorted.reduce(
            (total, generation) => total + generation.cost_nano_usd,
            0,
          ),
          single_generation: sorted.length === 1 && trace_id === first.id,
        },
      ];
    })
    .toSorted((a, b) => b.started_at.localeCompare(a.started_at));
};
