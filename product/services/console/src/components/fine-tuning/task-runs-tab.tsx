import { useState } from "react";

import { StageTimeline } from "@/components/fine-tuning/stage-timeline";
import {
  ThresholdProgress,
  UntrainedTaskState,
} from "@/components/fine-tuning/threshold-progress";
import {
  VersionActionButtons,
  VersionEvaluation,
  type VersionAction,
} from "@/components/fine-tuning/version-actions";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  STAGE_LABEL,
  isTerminalStage,
  type RunStage,
  type TaskRow,
  type TrainingRunRow,
  type VersionView,
} from "@/store/fine-tuning-types";
import {
  useMockFineTuning,
  useTaskRuns,
  useTaskStats,
  useTaskVersions,
} from "@/store/mock-fine-tuning";

const STAGE_BADGE_CLASS: Partial<Record<RunStage, string>> = {
  succeeded: "border-[#cadb87] bg-[#f2f7d9] text-[#475617]",
  failed: "border-destructive/25 bg-destructive/5 text-destructive",
  cancelled: "border-border bg-muted text-muted-foreground",
};

const ACTIVE_BADGE_CLASS = "border-[#a8c3e6] bg-[#e9f1fb] text-[#2c5282]";

const RunListItem = ({
  run,
  version,
  selected,
  onSelect,
}: {
  run: TrainingRunRow;
  version: VersionView | undefined;
  selected: boolean;
  onSelect: () => void;
}) => (
  <button
    type="button"
    onClick={onSelect}
    className={`block w-full border-b p-4 text-left last:border-b-0 hover:bg-muted/40 ${selected ? "bg-muted/60" : ""}`}
  >
    <div className="flex items-center justify-between gap-2">
      <span className="flex items-center gap-1.5 text-sm font-medium">
        {new Date(run.created_at).toLocaleDateString(undefined, {
          dateStyle: "medium",
        })}
        {run.trigger === "manual" ? (
          <span className="rounded border px-1 py-px text-[10px] font-normal text-muted-foreground">
            manual
          </span>
        ) : null}
      </span>
      <Badge
        variant="outline"
        className={STAGE_BADGE_CLASS[run.stage] ?? ACTIVE_BADGE_CLASS}
      >
        {STAGE_LABEL[run.stage]}
      </Badge>
    </div>
    <p className="mt-1 text-xs text-muted-foreground">
      {version ? (
        <code className="rounded bg-muted px-1 py-0.5 font-mono text-[0.9em] text-foreground">
          {version.model.id}
        </code>
      ) : null}
      {version && run.dataset ? " · " : null}
      {run.dataset ? `${run.dataset.usable.toLocaleString()} traces` : null}
    </p>
  </button>
);

export const TaskRunsTab = ({
  task,
  onVersionAction,
}: {
  task: TaskRow;
  onVersionAction: (action: VersionAction) => void;
}) => {
  const runs = useTaskRuns(task.id);
  const versions = useTaskVersions(task.id);
  const runLogs = useMockFineTuning((state) => state.run_logs);
  const cancelRun = useMockFineTuning((state) => state.cancelRun);
  const { usable_traces_since_last_run: usableSinceLastRun } = useTaskStats(
    task.id,
  );
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  const activeRun = runs.find((run) => !isTerminalStage(run.stage));
  const selectedRun =
    runs.find((run) => run.id === selectedRunId) ?? activeRun ?? runs[0];
  const versionOf = (run: TrainingRunRow) =>
    versions.find((version) => version.run.id === run.id);
  const selectedVersion = selectedRun ? versionOf(selectedRun) : undefined;

  if (!selectedRun) {
    return (
      <UntrainedTaskState
        title="No training runs yet"
        usableTraces={usableSinceLastRun}
      />
    );
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[280px_minmax(0,1fr)]">
      <section className="self-start overflow-hidden rounded-lg border bg-card">
        {!activeRun ? (
          <div className="border-b border-dashed p-4">
            <ThresholdProgress
              label="Next re-train"
              value={usableSinceLastRun}
              compact
            />
          </div>
        ) : null}
        {runs.map((run) => (
          <RunListItem
            key={run.id}
            run={run}
            version={versionOf(run)}
            selected={selectedRun.id === run.id}
            onSelect={() => setSelectedRunId(run.id)}
          />
        ))}
      </section>
      <Card className="self-start shadow-sm">
        <CardContent className="p-5">
          {selectedVersion ? (
            <div className="mb-6 border-b pb-5">
              <div className="mb-4 flex items-center justify-between gap-3">
                <span className="font-mono text-sm font-semibold">
                  {selectedVersion.model.id}
                </span>
                <div className="flex items-center gap-2">
                  <VersionActionButtons
                    version={selectedVersion}
                    onAction={onVersionAction}
                  />
                </div>
              </div>
              <VersionEvaluation
                version={selectedVersion}
                onAction={onVersionAction}
              />
            </div>
          ) : null}
          <StageTimeline
            run={selectedRun}
            events={runLogs[selectedRun.id] ?? []}
            onCancel={() => cancelRun(selectedRun.id)}
          />
        </CardContent>
      </Card>
    </div>
  );
};
