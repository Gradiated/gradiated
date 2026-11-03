import type { components } from "@/api/schema";
import type { TrainingRunRow, VersionView } from "./fine-tuning-types";

export const versionsForTask = (
  versions: readonly components["schemas"]["TaskVersion"][],
  runs: readonly TrainingRunRow[],
): VersionView[] => {
  const byId = new Map(runs.map((run) => [run.id, run]));

  return versions.map((version) => {
    const run = version.training_run_id
      ? byId.get(version.training_run_id)
      : undefined;

    return { ...version, run, summary: run?.evaluation ?? null };
  });
};

export const currentVersion = (
  versions: readonly VersionView[],
): VersionView | undefined =>
  versions.find((version) => version.is_production) ?? versions[0];

export const latestVersionEvaluation = ({
  latest_run: run,
  latest_version: version,
}: {
  latest_run: Pick<
    NonNullable<components["schemas"]["TaskListItem"]["latest_run"]>,
    "id" | "evaluation"
  > | null;
  latest_version?: Pick<
    components["schemas"]["TaskVersion"],
    "training_run_id"
  > | null;
}) =>
  !version || version.training_run_id === run?.id
    ? (run?.evaluation ?? null)
    : null;
