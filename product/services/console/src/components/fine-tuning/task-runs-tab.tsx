import { NextTraining } from "./next-training";
import { useState } from "react";

import { StageTimeline } from "@/components/fine-tuning/stage-timeline";
import { UntrainedTaskState } from "@/components/fine-tuning/untrained-task-state";
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
  useTaskHistory,
  useRunEvents,
  useTrainingMutation,
} from "@/hooks/use-training";
import { QueryState } from "./query-state";
import { toast } from "sonner";

import { errorMessage } from "@/lib/errors";
import { Button } from "@/components/ui/button";

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
    <p className="mt-2 space-y-1 text-xs text-muted-foreground">
      {version ? (
        <code className="block truncate rounded bg-muted px-1 py-0.5 font-mono text-[0.9em] text-foreground">
          {version.name}
        </code>
      ) : null}
      {run.dataset ? (
        <span className="block">
          {run.dataset.train.toLocaleString()} training examples
        </span>
      ) : null}
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
  const query = useTaskHistory(task);
  const { cancel, canEdit } = useTrainingMutation(task.name);
  const runs = query.data?.runs ?? [];
  const versions = query.data?.versions ?? [];
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  const activeRun = runs.find((run) => !isTerminalStage(run.stage));
  const selectedRun =
    runs.find((run) => run.id === selectedRunId) ?? activeRun ?? runs[0];
  const versionOf = (run: TrainingRunRow) =>
    versions.find((version) => version.training_run_id === run.id);
  const selectedVersion = selectedRun ? versionOf(selectedRun) : undefined;

  const events = useRunEvents(selectedRun?.id);

  if (query.isPending || query.error) return <QueryState query={query} />;

  if (!selectedRun) {
    return (
      <UntrainedTaskState
        title="No training runs yet"
        action={
          <div className="mt-3">
            <NextTraining schedule={task.training_schedule} />
          </div>
        }
      />
    );
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[280px_minmax(0,1fr)]">
      <section className="self-start overflow-hidden rounded-lg border bg-card">
        {!activeRun ? (
          <div className="border-b border-dashed p-4">
            <NextTraining schedule={task.training_schedule} />
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
                  {selectedVersion.name}
                </span>
                <div className="flex items-center gap-2">
                  <VersionActionButtons
                    version={selectedVersion}
                    onAction={onVersionAction}
                  />
                </div>
              </div>
              <VersionEvaluation version={selectedVersion} />
            </div>
          ) : null}
          <QueryState query={events} />
          {events.hasNextPage ? (
            <p className="mb-2 text-xs text-muted-foreground">
              Showing loaded events. Load more for later stages and progress.
            </p>
          ) : null}
          {events.hasNextPage ? (
            <Button
              variant="outline"
              disabled={events.isFetchingNextPage}
              onClick={() => void events.fetchNextPage()}
            >
              Load more events
            </Button>
          ) : null}
          {!events.isPending && !events.error ? (
            <StageTimeline
              run={selectedRun}
              {...(canEdit && !cancel.isPending
                ? {
                    onCancel: () =>
                      cancel.mutate(selectedRun.id, {
                        onError: (error) =>
                          toast.error(
                            errorMessage(
                              error,
                              "The run could not be cancelled.",
                            ),
                          ),
                      }),
                  }
                : {})}
              events={events.data?.pages.flatMap((page) => page.data) ?? []}
            />
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
};
