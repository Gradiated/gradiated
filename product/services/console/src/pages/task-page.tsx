import { Button } from "@/components/ui/button";
import { useTaskHistory } from "@/hooks/use-training";
import { isTerminalStage, type TaskRow } from "@/store/fine-tuning-types";
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
import { OptionTabs, type Option } from "@/pages/option-select";
import { useTask } from "@/hooks/use-training";
import { QueryState } from "@/components/fine-tuning/query-state";
import { useProductContext } from "@/hooks/use-product-context";

const TABS = [
  { value: "model", label: "Model" },
  { value: "runs", label: "Training runs" },
  { value: "traces", label: "Data" },
  { value: "settings", label: "Settings" },
] as const satisfies readonly Option<string>[];

type TabKey = (typeof TABS)[number]["value"];

export const TaskPage = () => (
  <TrainingGate>
    <ScopedTaskPage />
  </TrainingGate>
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

  if (query.isPending || query.error) {
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
  const runs = history.data?.runs ?? [];
  const training = runs.some((run) => !isTerminalStage(run.stage));
  return (
    <Button
      disabled
      variant={history.data?.versions.length ? "outline" : "default"}
    >
      <RotateCw className={`size-4 ${training ? "animate-spin" : ""}`} />
      {training ? "Re-training…" : runs.length ? "Re-train" : "Train now"}
    </Button>
  );
};
