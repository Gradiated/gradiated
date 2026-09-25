import { Link, useNavigate, useSearch } from "@tanstack/react-router";
import { Check, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

import { TrainingGate } from "@/components/fine-tuning/training-gate";
import { ConnectDialog } from "@/components/fine-tuning/connect-dialog";
import { ConnectSnippet } from "@/components/fine-tuning/connect-snippet";
import {
  OutcomeBar,
  RatioLabel,
} from "@/components/fine-tuning/evaluation-panel";
import {
  costAdvantage,
  costPer1kRequests,
  outputSpeed,
  speedAdvantage,
} from "@/components/fine-tuning/evaluation-ratios";
import {
  ModelSelect,
  SettingRow,
  SettingsCard,
} from "@/components/fine-tuning/settings-card";
import { Button } from "@/components/ui/button";
import { TraceCaptureSettings } from "@/components/fine-tuning/trace-capture-settings";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { TabsContent } from "@/components/ui/tabs";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { formatPercent } from "@/lib/format";
import { ConsolePage } from "@/pages/console-page";
import { OptionTabs, type Option } from "@/pages/option-select";
import { useConnectFlow } from "@/store/connect-flow";
import {
  EVALUATION_JUDGE_ALLOWLIST,
  TRAINING_TRACE_THRESHOLD,
  type JudgeOutcome,
  type TaskRow,
} from "@/store/fine-tuning-types";
import { currentVersion } from "@/store/fine-tuning-views";
import {
  useLiveRunTicker,
  useMockFineTuning,
  useTaskStats,
  useTaskVersions,
} from "@/store/mock-fine-tuning";

const TABS = [
  { value: "tasks", label: "Models" },
  { value: "settings", label: "Settings" },
] as const satisfies readonly Option<string>[];

const FIRST_REQUEST_DELAY_MS = 6_000;

const trainedDate = new Intl.DateTimeFormat(undefined, {
  day: "numeric",
  month: "short",
});

export const TasksPage = () => (
  <TrainingGate>
    <TasksPageBody />
  </TrainingGate>
);

const TasksPageBody = () => {
  const navigate = useNavigate();
  const { empty } = useSearch({ from: "/tasks" });
  const allTasks = useMockFineTuning((state) => state.tasks);
  const workspace = useMockFineTuning((state) => state.workspace);
  const setEvaluationJudge = useMockFineTuning(
    (state) => state.setEvaluationJudge,
  );
  const connectionStatus = useConnectFlow((state) => state.status);
  const connectTaskSlug = useConnectFlow((state) => state.taskSlug);
  const markConnected = useConnectFlow((state) => state.markConnected);
  const tasks = empty ? [] : allTasks;
  const [tab, setTab] = useState<(typeof TABS)[number]["value"]>("tasks");
  const [connectOpen, setConnectOpen] = useState(false);

  useLiveRunTicker();

  useEffect(() => {
    if (!empty || connectionStatus === "connected") return;

    const timeout = window.setTimeout(markConnected, FIRST_REQUEST_DELAY_MS);

    return () => window.clearTimeout(timeout);
  }, [empty, connectionStatus, markConnected]);

  return (
    <ConsolePage
      page="tasks"
      title="Training"
      actions={
        tasks.length ? (
          <Button variant="outline" onClick={() => setConnectOpen(true)}>
            Train a model
          </Button>
        ) : null
      }
    >
      <OptionTabs value={tab} options={TABS} onValueChange={setTab}>
        <TabsContent value="tasks">
          {tasks.length ? (
            <section className="overflow-hidden rounded-lg border bg-card">
              <Table>
                <TableHeader className="bg-muted/40">
                  <TableRow className="hover:bg-transparent">
                    <TableHead className="h-11 pl-5">Task</TableHead>
                    <TableHead className="h-11 px-4">Model</TableHead>
                    <TableHead className="h-11 px-4">Replaces</TableHead>
                    <TableHead className="h-11 px-4">Cost</TableHead>
                    <TableHead className="h-11 px-4">Speed</TableHead>
                    <TableHead className="h-11 px-4">Quality</TableHead>
                    <TableHead className="h-11 pr-5">Trained</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {tasks.map((task) => (
                    <TaskRowView
                      key={task.id}
                      task={task}
                      onOpen={() =>
                        void navigate({
                          to: "/tasks/$taskId",
                          params: { taskId: task.id },
                        })
                      }
                    />
                  ))}
                </TableBody>
              </Table>
            </section>
          ) : (
            <div className="rounded-xl border bg-card p-6 shadow-sm">
              <h3 className="text-base font-semibold">No tasks yet</h3>
              <p className="mt-1 mb-5 max-w-xl text-sm leading-6 text-muted-foreground">
                Add two headers to your OpenAI or Anthropic client. A task
                appears here with its first request, and you keep your provider
                key.
              </p>
              <ConnectSnippet />
              <div className="mt-5 flex items-center gap-2 border-t pt-4 text-sm">
                {connectionStatus === "connected" ? (
                  <>
                    <Check className="size-4 text-[#475617]" />
                    <span>
                      First request received ·{" "}
                      <span className="font-mono text-xs">
                        {connectTaskSlug}
                      </span>
                    </span>
                  </>
                ) : (
                  <>
                    <Loader2 className="size-4 animate-spin text-muted-foreground" />
                    <span className="text-muted-foreground">
                      Waiting for your first request…
                    </span>
                  </>
                )}
              </div>
            </div>
          )}
        </TabsContent>

        <TabsContent value="settings">
          <SettingsCard>
            <SettingRow
              title="Judge model"
              description="This is the model used to compare fine-tuned models vs existing models to decide which is better."
            >
              <ModelSelect
                label="Judge model"
                value={workspace.evaluation_judge}
                models={EVALUATION_JUDGE_ALLOWLIST}
                onChange={setEvaluationJudge}
              />
            </SettingRow>
            <TraceCaptureSettings />
          </SettingsCard>
        </TabsContent>
      </OptionTabs>

      <ConnectDialog open={connectOpen} onOpenChange={setConnectOpen} />
    </ConsolePage>
  );
};

const TaskRowView = ({
  task,
  onOpen,
}: {
  task: TaskRow;
  onOpen: () => void;
}) => {
  const version = currentVersion(useTaskVersions(task.id));
  const { usable_traces_since_last_run: usableSinceLastRun } = useTaskStats(
    task.id,
  );

  return (
    <TableRow className="cursor-pointer" onClick={onOpen}>
      <TableCell className="h-14 pl-5 font-medium">
        <Link
          to="/tasks/$taskId"
          params={{ taskId: task.id }}
          onClick={(event) => event.stopPropagation()}
          className="rounded-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        >
          {task.slug}
        </Link>
      </TableCell>
      <TableCell className="px-4">
        {version ? (
          <span className="flex flex-wrap items-center gap-1.5">
            <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
              {version.model.id}
            </code>
            {!version.is_production ? (
              <span className="text-xs text-muted-foreground">
                not promoted
              </span>
            ) : null}
          </span>
        ) : (
          <span className="text-muted-foreground">No model yet</span>
        )}
      </TableCell>
      <TableCell className="px-4">
        <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-muted-foreground">
          {task.comparison_model_id}
        </code>
      </TableCell>
      <TableCell className="px-4 tabular-nums">
        {version ? (
          <RatioLabel
            ratio={costAdvantage(version.summary)}
            detail={costPer1kRequests(version.summary)}
          />
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </TableCell>
      <TableCell className="px-4 tabular-nums">
        {version ? (
          <RatioLabel
            ratio={speedAdvantage(version.summary)}
            detail={outputSpeed(version.summary)}
          />
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </TableCell>
      <TableCell className="px-4">
        {version ? (
          <QualityBar result={version.summary.vs_comparison} />
        ) : (
          <span className="text-muted-foreground tabular-nums">
            {usableSinceLastRun} / {TRAINING_TRACE_THRESHOLD} traces
          </span>
        )}
      </TableCell>
      <TableCell className="pr-5 text-muted-foreground">
        {version ? trainedDate.format(new Date(version.model.created_at)) : "—"}
      </TableCell>
    </TableRow>
  );
};

const QualityBar = ({ result }: { result: JudgeOutcome }) => (
  <Tooltip>
    <TooltipTrigger asChild>
      <span className="block w-40 cursor-default">
        <OutcomeBar outcome={result} height="h-2" labels={false} />
      </span>
    </TooltipTrigger>
    <TooltipContent side="top" className="text-xs">
      vs {result.comparator_model_id}: better {formatPercent(result.win)} ·
      equivalent {formatPercent(result.tie)} · worse{" "}
      {formatPercent(result.loss)} · unresolved{" "}
      {formatPercent(result.unresolved)} overall. The bar shows resolved
      comparisons only.
    </TooltipContent>
  </Tooltip>
);
