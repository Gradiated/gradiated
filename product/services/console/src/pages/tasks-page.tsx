import { useNavigate, useSearch } from "@tanstack/react-router";
import { Check, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { TrainingGate } from "@/components/fine-tuning/training-gate";
import { ConnectDialog } from "@/components/fine-tuning/connect-dialog";
import { ConnectSnippet } from "@/components/fine-tuning/connect-snippet";
import {
  OutcomeBar,
  usdFromNano,
} from "@/components/fine-tuning/evaluation-panel";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useProductContext } from "@/hooks/use-product-context";
import {
  EVALUATION_JUDGE_ALLOWLIST,
  TRAINING_TRACE_THRESHOLD,
  useMockFineTuning,
  versionsForTask,
  type EvaluationJudge,
  type JudgeOutcome,
  type TaskRow,
  type TaskStats,
  type VersionView,
} from "@/store/mock-fine-tuning";

const pct = (value: number) => `${Math.round(value * 100)}%`;
const formatDate = (value: string) =>
  new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short" }).format(
    new Date(value),
  );

export const TasksPage = () => (
  <TrainingGate>
    <TasksPageBody />
  </TrainingGate>
);

const TasksPageBody = () => {
  const context = useProductContext();
  const navigate = useNavigate();
  const { empty } = useSearch({ from: "/tasks" });
  const store = useMockFineTuning();
  const {
    workspace,
    stats,
    setTraceCapture,
    setEvaluationJudge,
    connection_status,
    connect_task_slug,
    markConnected,
  } = store;
  const tasks = empty ? [] : store.tasks;
  const [tab, setTab] = useState<"tasks" | "settings">("tasks");
  const [connectOpen, setConnectOpen] = useState(false);

  // Mock: the first request "arrives" a few seconds after the empty state is shown.
  useEffect(() => {
    if (!empty || connection_status === "connected") return;
    const t = window.setTimeout(markConnected, 6000);
    return () => window.clearTimeout(t);
  }, [empty, connection_status, markConnected]);

  return (
    <AppShell
      user={context.user}
      organizationId={context.organizationId}
      workspaces={context.workspaces}
      workspaceId={context.workspaceId}
      onSelectOrganization={context.selectOrganization}
      onSelectWorkspace={context.selectWorkspace}
      onSignOut={context.signOut}
      activePage="tasks"
      pageTitle="Training"
    >
      <main className="min-w-0 flex-1 px-5 py-8 lg:px-10 lg:py-10">
        <div className="mx-auto max-w-5xl">
          <div className="mb-6 flex items-end justify-between gap-5">
            <h1 className="text-3xl font-semibold tracking-[-0.035em]">
              Training
            </h1>
            {tasks.length ? (
              <Button variant="outline" onClick={() => setConnectOpen(true)}>
                Train a model
              </Button>
            ) : null}
          </div>

          <Tabs
            value={tab}
            onValueChange={(v) => setTab(v as "tasks" | "settings")}
          >
            <TabsList>
              <TabsTrigger value="tasks">Models</TabsTrigger>
              <TabsTrigger value="settings">Settings</TabsTrigger>
            </TabsList>

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
                          stats={stats[task.id]}
                          version={
                            versionsForTask(store, task.id).find(
                              (v) => v.is_production,
                            ) ?? versionsForTask(store, task.id)[0]
                          }
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
                    appears here with its first request, and you keep your
                    provider key.
                  </p>
                  <ConnectSnippet />
                  <div className="mt-5 flex items-center gap-2 border-t pt-4 text-sm">
                    {connection_status === "connected" ? (
                      <>
                        <Check className="size-4 text-[#475617]" />
                        <span>
                          First request received ·{" "}
                          <span className="font-mono text-xs">
                            {connect_task_slug}
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
              <div className="max-w-2xl divide-y rounded-lg border bg-card">
                <div className="flex items-start justify-between gap-6 p-5">
                  <div>
                    <p className="text-sm font-medium">Judge model</p>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">
                      This is the model used to compare fine-tuned models vs
                      existing models to decide which is better.
                    </p>
                  </div>
                  <Select
                    value={workspace.evaluation_judge}
                    onValueChange={(v) =>
                      setEvaluationJudge(v as EvaluationJudge)
                    }
                  >
                    <SelectTrigger className="w-64 font-mono text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {EVALUATION_JUDGE_ALLOWLIST.map((m) => (
                        <SelectItem
                          key={m}
                          value={m}
                          className="font-mono text-xs"
                        >
                          {m}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="flex items-start justify-between gap-6 p-5">
                  <div>
                    <p className="text-sm font-medium">Trace capture</p>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">
                      Models are fine-tuned and evaluated on these. They are
                      kept for 30 days and then deleted.
                    </p>
                  </div>
                  <Switch
                    checked={workspace.trace_capture_enabled}
                    onCheckedChange={setTraceCapture}
                    aria-label="Trace capture"
                  />
                </div>
              </div>
            </TabsContent>
          </Tabs>
        </div>
      </main>

      <ConnectDialog open={connectOpen} onOpenChange={setConnectOpen} />
    </AppShell>
  );
};

const TaskRowView = ({
  task,
  stats,
  version,
  onOpen,
}: {
  task: TaskRow;
  stats: TaskStats | undefined;
  version: VersionView | undefined;
  onOpen: () => void;
}) => (
  <TableRow className="cursor-pointer" onClick={onOpen}>
    <TableCell className="h-14 pl-5 font-medium">{task.slug}</TableCell>
    <TableCell className="px-4">
      {version ? (
        <span className="flex flex-wrap items-center gap-1.5">
          <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
            {version.model.id}
          </code>
          {!version.is_production ? (
            <span className="text-xs text-muted-foreground">not promoted</span>
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
        <Ratio
          // Cheaper when the fine-tuned model costs less per request than the comparison model.
          value={
            version.summary.cost_per_request_nano_usd.comparison /
            version.summary.cost_per_request_nano_usd.fine_tuned
          }
          good="cheaper"
          bad="more expensive"
          detail={`${usdFromNano(version.summary.cost_per_request_nano_usd.fine_tuned * 1000)} vs ${usdFromNano(version.summary.cost_per_request_nano_usd.comparison * 1000)} per 1k requests`}
        />
      ) : (
        <span className="text-muted-foreground">—</span>
      )}
    </TableCell>
    <TableCell className="px-4 tabular-nums">
      {version ? (
        <Ratio
          value={
            version.summary.output_tokens_per_second.fine_tuned /
            Math.max(1, version.summary.output_tokens_per_second.comparison)
          }
          good="faster"
          bad="slower"
          detail={`${version.summary.output_tokens_per_second.fine_tuned} vs ${version.summary.output_tokens_per_second.comparison} output tokens/s`}
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
          {stats?.usable_traces_since_last_run ?? 0} /{" "}
          {TRAINING_TRACE_THRESHOLD} traces
        </span>
      )}
    </TableCell>
    <TableCell className="pr-5 text-muted-foreground">
      {version ? formatDate(version.model.created_at) : "—"}
    </TableCell>
  </TableRow>
);

/** A ratio against the model being replaced: `value` > 1 is good ("5.2× cheaper" / "1.6× faster"). */
const Ratio = ({
  value,
  good,
  bad,
  detail,
}: {
  value: number;
  good: string;
  bad: string;
  detail: string;
}) => {
  const isGood = value >= 1;
  const factor = isGood ? value : 1 / value;
  const label = `${factor >= 10 ? Math.round(factor) : factor.toFixed(1)}× ${isGood ? good : bad}`;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span
          className={`font-medium ${isGood ? "text-[#475617]" : "text-amber-800"}`}
        >
          {label}
        </span>
      </TooltipTrigger>
      <TooltipContent side="top" className="text-xs">
        {detail}
      </TooltipContent>
    </Tooltip>
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
      vs {result.comparator_model_id}: better {pct(result.win)} · equivalent{" "}
      {pct(result.tie)} · worse {pct(result.loss)} · unresolved{" "}
      {pct(result.unresolved)} overall. The bar shows resolved comparisons only.
    </TooltipContent>
  </Tooltip>
);
