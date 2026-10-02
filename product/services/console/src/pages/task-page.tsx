import { Skeleton } from "@/components/ui/skeleton";
import { toast } from "sonner";
import { Link, useParams } from "@tanstack/react-router";
import { ArrowLeft, RotateCw } from "lucide-react";
import { useState } from "react";

import { TaskModelTab } from "@/components/fine-tuning/task-model-tab";
import { TaskRunsTab } from "@/components/fine-tuning/task-runs-tab";
import { TaskSettingsTab } from "@/components/fine-tuning/task-settings-tab";
import { TaskTracesTab } from "@/components/fine-tuning/task-traces-tab";
import { TrainingGate } from "@/components/fine-tuning/training-gate";
import {
  VersionActionDialog,
  type VersionAction,
} from "@/components/fine-tuning/version-actions";
import { TabsContent } from "@/components/ui/tabs";
import { ConsolePage } from "@/pages/console-page";
import { OptionTabs, type Option } from "@/components/option-select";
import {
  useTask,
  useTaskHistory,
  useTrainingMutation,
} from "@/hooks/use-training";
import { isTerminalStage, type TaskRow } from "@/store/fine-tuning-types";
import { Button } from "@/components/ui/button";
import { QueryState } from "@/components/fine-tuning/query-state";
import { useProductContext } from "@/hooks/use-product-context";

const TABS = [
  { value: "model", label: "Model" },
  { value: "runs", label: "Training runs" },
  { value: "traces", label: "Data" },
  { value: "settings", label: "Settings" },
] as const satisfies readonly Option<string>[];

type TabKey = (typeof TABS)[number]["value"];

export const TaskPage = () => {
  const { taskId } = useParams({ from: "/tasks/$taskId" });

  return (
    <TrainingGate loadingContent={<TaskLoadingState name={taskId} />}>
      <ScopedTaskPage />
    </TrainingGate>
  );
};

const TaskLoadingState = ({ name }: { name: string }) => (
  <ConsolePage page="tasks" title={name}>
    <div role="status" aria-label="Loading task" className="space-y-6">
      <div className="flex gap-4 border-b pb-2">
        {TABS.map(({ value }) => (
          <Skeleton key={value} className="h-10 w-28" />
        ))}
      </div>
      <div className="space-y-4 rounded-xl border bg-card p-5">
        <Skeleton className="h-8 w-64 max-w-full" />
        <Skeleton className="h-4 w-80 max-w-full" />
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-4 w-48" />
      </div>
      <Skeleton className="h-72 w-full" />
    </div>
  </ConsolePage>
);

const ScopedTaskPage = () => {
  const { workspaceId } = useProductContext();
  const { taskId } = useParams({ from: "/tasks/$taskId" });

  return <TaskPageBody key={`${workspaceId}:${taskId}`} />;
};

const TaskPageBody = () => {
  const { taskId } = useParams({ from: "/tasks/$taskId" });
  const query = useTask(taskId);
  const task = query.data;
  const [tab, setTab] = useState<TabKey>("model");
  const [versionAction, setVersionAction] = useState<VersionAction | null>(
    null,
  );

  if (query.isPending) return <TaskLoadingState name={taskId} />;

  if (query.error) {
    return (
      <ConsolePage page="tasks" title="Training">
        <QueryState query={query} />
      </ConsolePage>
    );
  }

  if (!task) {
    return (
      <ConsolePage page="tasks" title="Task not found">
        <Link to="/tasks" className="text-sm text-muted-foreground underline">
          Back to tasks
        </Link>
      </ConsolePage>
    );
  }

  return (
    <ConsolePage
      page="tasks"
      title={task.name}
      actions={<TrainButton task={task} />}
      back={
        <Link
          to="/tasks"
          className="mb-4 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-3.5" />
          Tasks
        </Link>
      }
    >
      <OptionTabs value={tab} options={TABS} onValueChange={setTab}>
        <TabsContent value="model">
          <TaskModelTab
            task={task}
            onVersionAction={setVersionAction}
            onShowRuns={() => setTab("runs")}
          />
        </TabsContent>
        <TabsContent value="runs">
          <TaskRunsTab task={task} onVersionAction={setVersionAction} />
        </TabsContent>
        <TabsContent value="traces">
          <TaskTracesTab task={task} />
        </TabsContent>
        <TabsContent value="settings">
          <TaskSettingsTab task={task} />
        </TabsContent>
      </OptionTabs>

      {versionAction ? (
        <VersionActionDialog
          task={task}
          action={versionAction}
          onClose={() => setVersionAction(null)}
        />
      ) : null}
    </ConsolePage>
  );
};

const TrainButton = ({ task }: { task: TaskRow }) => {
  const history = useTaskHistory(task);
  const { start, canEdit } = useTrainingMutation(task.name);
  const [acceptedId, setAcceptedId] = useState<string | null>(null);
  const runs = history.data?.runs ?? [];
  const training = runs.some((run) => !isTerminalStage(run.stage));
  const starting =
    acceptedId !== null && !runs.some((run) => run.id === acceptedId);

  return (
    <div className="space-y-2 text-right">
      <Button
        variant={history.data?.versions.length ? "outline" : "default"}
        disabled={
          !canEdit ||
          history.isPending ||
          Boolean(history.error) ||
          start.isPending ||
          starting ||
          training
        }
        onClick={() =>
          start.mutate(task.id, {
            onSuccess: ({ id }) => setAcceptedId(id),
            onError: (error) =>
              toast.error("Could not start training", {
                description: error.message,
              }),
          })
        }
      >
        <RotateCw className={`size-4 ${training ? "animate-spin" : ""}`} />
        {start.isPending || starting
          ? "Starting…"
          : training
            ? "Re-training…"
            : runs.length
              ? "Re-train"
              : "Train now"}
      </Button>
    </div>
  );
};
