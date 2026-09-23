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
import { Button } from "@/components/ui/button";
import { TabsContent } from "@/components/ui/tabs";
import { ConsolePage } from "@/pages/console-page";
import { OptionTabs, type Option } from "@/pages/option-select";
import { isTerminalStage, type TaskRow } from "@/store/fine-tuning-types";
import {
  useLiveRunTicker,
  useMockFineTuning,
  useTaskRuns,
  useTaskVersions,
} from "@/store/mock-fine-tuning";

const TABS = [
  { value: "model", label: "Model" },
  { value: "runs", label: "Training runs" },
  { value: "traces", label: "Data" },
  { value: "settings", label: "Settings" },
] as const satisfies readonly Option<string>[];

type TabKey = (typeof TABS)[number]["value"];

export const TaskPage = () => (
  <TrainingGate>
    <TaskPageBody />
  </TrainingGate>
);

const TaskPageBody = () => {
  const { taskId } = useParams({ from: "/tasks/$taskId" });
  const task = useMockFineTuning((state) =>
    state.tasks.find((candidate) => candidate.id === taskId),
  );
  const [tab, setTab] = useState<TabKey>("model");
  const [versionAction, setVersionAction] = useState<VersionAction | null>(
    null,
  );

  useLiveRunTicker();

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
      title={task.slug}
      back={
        <Link
          to="/tasks"
          className="mb-4 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-3.5" />
          Tasks
        </Link>
      }
      actions={<TrainButton task={task} />}
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
  const runs = useTaskRuns(task.id);
  const hasVersions = useTaskVersions(task.id).length > 0;
  const createRun = useMockFineTuning((state) => state.createRun);

  const training = runs.some((run) => !isTerminalStage(run.stage));
  const idleLabel = runs.length ? "Re-train" : "Train now";

  return (
    <Button
      onClick={() => createRun(task.id)}
      disabled={training}
      variant={hasVersions ? "outline" : "default"}
    >
      <RotateCw className={`size-4 ${training ? "animate-spin" : ""}`} />
      {training ? "Re-training…" : idleLabel}
    </Button>
  );
};
