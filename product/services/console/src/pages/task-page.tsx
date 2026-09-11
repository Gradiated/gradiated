import { Link, useParams } from "@tanstack/react-router";
import {
  ArrowLeft,
  ChevronDown,
  FlaskConical,
  MoreHorizontal,
  RotateCw,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";

import { AppShell } from "@/components/app-shell";
import { TrainingGate } from "@/components/fine-tuning/training-gate";
import { DownloadAdapterDialog } from "@/components/fine-tuning/download-adapter-dialog";
import { EvaluationPanel } from "@/components/fine-tuning/evaluation-panel";
import { HoldoutResultsSheet } from "@/components/fine-tuning/holdout-results-sheet";
import { StageTimeline } from "@/components/fine-tuning/stage-timeline";
import { TraceSheet, formatNano } from "@/components/fine-tuning/trace-sheet";
import { UseModelDialog } from "@/components/fine-tuning/use-model-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useProductContext } from "@/hooks/use-product-context";
import { formatUsd } from "@/lib/format";
import {
  STAGE_LABEL,
  TERMINAL_STAGES,
  TRAINING_TRACE_THRESHOLD,
  evaluationResults,
  priceForModel,
  traceSummaries,
  useMockFineTuning,
  versionsForTask,
  type RunStage,
  type TaskRow,
  type TaskStats,
  type TraceGenerationRow,
  type VersionView,
} from "@/store/mock-fine-tuning";

type TabKey = "model" | "runs" | "traces" | "settings";
const VERSIONS_PAGE = 5;
const TRACES_PAGE = 20;

const pct = (value: number) => `${Math.round(value * 100)}%`;
const stageBadgeClass = (stage: RunStage): string => {
  if (stage === "succeeded")
    return "border-[#cadb87] bg-[#f2f7d9] text-[#475617]";
  if (stage === "failed")
    return "border-destructive/25 bg-destructive/5 text-destructive";
  if (stage === "cancelled")
    return "border-border bg-muted text-muted-foreground";
  return "border-[#a8c3e6] bg-[#e9f1fb] text-[#2c5282]";
};
const formatDate = (value: string) =>
  new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(
    new Date(value),
  );
const formatTime = (value: string) =>
  new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
const formatDuration = (ms: number) =>
  ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
const compact = (value: number) =>
  new Intl.NumberFormat(undefined, {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(value);
const dayLabel = (value: string) =>
  new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(
    new Date(value),
  );

export const TaskPage = () => (
  <TrainingGate>
    <TaskPageBody />
  </TrainingGate>
);

const TaskPageBody = () => {
  const context = useProductContext();
  const { taskId } = useParams({ from: "/tasks/$taskId" });
  const store = useMockFineTuning();
  const {
    tasks,
    models,
    training_runs,
    run_logs,
    traces,
    conversations,
    stats,
    createRun,
    cancelRun,
    setTaskBaseModel,
    setTaskComparisonModel,
    promote,
  } = store;

  const [tab, setTab] = useState<TabKey>("model");
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [openVersionId, setOpenVersionId] = useState<string | null>(null);
  const [useVersionId, setUseVersionId] = useState<string | null>(null);
  const [downloadVersionId, setDownloadVersionId] = useState<string | null>(
    null,
  );
  const [resultsVersionId, setResultsVersionId] = useState<string | null>(null);
  const [promoteVersionId, setPromoteVersionId] = useState<string | null>(null);
  const [versionsShown, setVersionsShown] = useState(VERSIONS_PAGE);
  const [tracesShown, setTracesShown] = useState(TRACES_PAGE);

  const task = tasks.find((t) => t.id === taskId);
  const taskStats = task ? stats[task.id] : undefined;
  const versions = useMemo(
    () => (task ? versionsForTask(store, task.id) : []),
    [store, task],
  );
  const runs = useMemo(
    () =>
      training_runs
        .filter((r) => r.task_id === taskId)
        .sort((a, b) => b.created_at.localeCompare(a.created_at)),
    [training_runs, taskId],
  );
  const summaries = useMemo(
    () => (task ? traceSummaries(traces, task.slug) : []),
    [traces, task],
  );
  const trainableBases = useMemo(
    () => models.filter((m) => m.trainable && m.workspace_id === null),
    [models],
  );
  // Comparison candidates: provider models seen in this task's traffic, plus whatever is set now.
  const comparisonOptions = useMemo(() => {
    const seen = traces
      .filter((r) => task && r.task === task.slug)
      .map((r) => r.model);
    return [...new Set([...(task ? [task.comparison_model_id] : []), ...seen])];
  }, [traces, task]);

  const activeRun = runs.find((r) => !TERMINAL_STAGES.includes(r.stage));
  const selectedRun =
    runs.find((r) => r.id === selectedRunId) ?? activeRun ?? runs[0];
  const selectedRunVersion = versions.find((v) => v.run.id === selectedRun?.id);
  // Lead with production. Until a member promotes one, the newest version is shown as a candidate.
  const production = versions.find((v) => v.is_production);
  const current = production ?? versions[0];
  const otherVersions = versions.filter((v) => v !== current);
  const useVersion = versions.find((v) => v.model.id === useVersionId);
  const downloadVersion = versions.find(
    (v) => v.model.id === downloadVersionId,
  );
  const promoteVersion = versions.find((v) => v.model.id === promoteVersionId);
  const resultsVersion =
    versions.find((v) => v.model.id === resultsVersionId) ?? null;
  const holdoutResults = useMemo(
    () =>
      resultsVersion && task
        ? evaluationResults(resultsVersion, conversations, traces, task.slug)
        : [],
    [resultsVersion, conversations, traces, task],
  );
  const selectedTrace =
    summaries.find((t) => t.trace_id === selectedTraceId) ?? null;
  const selectedTraceGenerations: TraceGenerationRow[] = useMemo(
    () =>
      selectedTrace
        ? traces
            .filter((r) => r.trace_id === selectedTrace.trace_id)
            .sort((a, b) => a.captured_at.localeCompare(b.captured_at))
        : [],
    [traces, selectedTrace],
  );

  const shell = (children: React.ReactNode, title: string) => (
    <AppShell
      user={context.user}
      organizationId={context.organizationId}
      workspaces={context.workspaces}
      workspaceId={context.workspaceId}
      onSelectOrganization={context.selectOrganization}
      onSelectWorkspace={context.selectWorkspace}
      onSignOut={context.signOut}
      activePage="tasks"
      pageTitle={title}
    >
      {children}
    </AppShell>
  );

  if (!task) {
    return shell(
      <main className="flex min-h-[60vh] flex-1 items-center justify-center">
        <p className="text-sm text-muted-foreground">Task not found.</p>
      </main>,
      "Task",
    );
  }

  const currentModelFor = (v: VersionView) =>
    production && production.model.id !== v.model.id
      ? production.model.id
      : task.comparison_model_id;
  const usableSinceLastRun = taskStats?.usable_traces_since_last_run ?? 0;

  const versionMeta = (version: VersionView) => (
    <>
      based on{" "}
      <code className="rounded bg-muted px-1 py-0.5 font-mono text-[0.9em]">
        {version.model.base_model_id}
      </code>{" "}
      · {formatDate(version.model.created_at)} ·{" "}
      {version.run.dataset?.usable.toLocaleString() ?? "—"} traces
    </>
  );

  // Previous versions: an accordion, all collapsed by default; actions live in a ⋯ menu.
  const previousRow = (version: VersionView) => {
    const isOpen = openVersionId === version.model.id;
    return (
      <div key={version.model.id} className="border-b last:border-b-0">
        <div
          role="button"
          tabIndex={0}
          onClick={() => setOpenVersionId(isOpen ? null : version.model.id)}
          onKeyDown={(e) =>
            e.key === "Enter" &&
            setOpenVersionId(isOpen ? null : version.model.id)
          }
          className="flex cursor-pointer items-center justify-between gap-4 px-5 py-3 text-left hover:bg-muted/30"
        >
          <div className="flex min-w-0 items-center gap-3">
            <ChevronDown
              className={`size-4 shrink-0 text-muted-foreground transition-transform ${isOpen ? "" : "-rotate-90"}`}
            />
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-sm font-medium">
                  {version.model.id}
                </span>
              </div>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {versionMeta(version)}
              </p>
            </div>
          </div>
          <div onClick={(e) => e.stopPropagation()}>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="size-8 shrink-0"
                  aria-label={`Actions for ${version.model.id}`}
                >
                  <MoreHorizontal className="size-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem
                  onSelect={() => setPromoteVersionId(version.model.id)}
                >
                  Promote to production
                </DropdownMenuItem>
                <DropdownMenuItem
                  onSelect={() => setUseVersionId(version.model.id)}
                >
                  Use this version
                </DropdownMenuItem>
                <DropdownMenuItem
                  onSelect={() => setDownloadVersionId(version.model.id)}
                >
                  Download adapter
                </DropdownMenuItem>
                <DropdownMenuItem
                  onSelect={() => setResultsVersionId(version.model.id)}
                >
                  View test results
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
        {isOpen ? (
          <div className="border-t px-5 py-5">
            <EvaluationPanel
              summary={version.summary}
              onViewResults={() => setResultsVersionId(version.model.id)}
            />
          </div>
        ) : null}
      </div>
    );
  };

  return shell(
    <>
      <main className="min-w-0 flex-1 px-5 py-8 lg:px-10 lg:py-10">
        <div className="mx-auto max-w-5xl">
          <Link
            to="/tasks"
            className="mb-4 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="size-3.5" />
            Tasks
          </Link>

          <div className="mb-6 flex items-start justify-between gap-4">
            <h1 className="font-mono text-2xl font-semibold tracking-[-0.02em]">
              {task.slug}
            </h1>
            <Button
              onClick={() => createRun(task.id)}
              disabled={Boolean(activeRun)}
              variant={versions.length ? "outline" : "default"}
            >
              <RotateCw
                className={`size-4 ${activeRun ? "animate-spin" : ""}`}
              />
              {activeRun
                ? "Re-training…"
                : runs.length
                  ? "Re-train"
                  : "Train now"}
            </Button>
          </div>

          <Tabs value={tab} onValueChange={(v) => setTab(v as TabKey)}>
            <TabsList>
              <TabsTrigger value="model">Model</TabsTrigger>
              <TabsTrigger value="runs">Training runs</TabsTrigger>
              <TabsTrigger value="traces">Data</TabsTrigger>
              <TabsTrigger value="settings">Settings</TabsTrigger>
            </TabsList>

            {/* ---------------------------------------------------------------- Model */}
            <TabsContent value="model">
              <div className="space-y-5">
                {current ? (
                  <>
                    <section className="rounded-xl border bg-card shadow-sm">
                      <div className="flex items-start justify-between gap-4 px-5 py-4">
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <h2 className="font-mono text-lg font-semibold tracking-[-0.02em]">
                              {current.is_production
                                ? task.slug
                                : current.model.id}
                            </h2>
                            {current.is_production ? (
                              <Badge className="bg-[#6e7f31] text-white hover:bg-[#6e7f31]">
                                Production
                              </Badge>
                            ) : (
                              <Badge
                                variant="outline"
                                className="text-muted-foreground"
                              >
                                Not in production
                              </Badge>
                            )}
                          </div>
                          <p className="mt-1 text-xs text-muted-foreground">
                            {current.is_production ? (
                              <>
                                <code className="rounded bg-muted px-1 py-0.5 font-mono text-[0.9em]">
                                  {current.model.id}
                                </code>{" "}
                                ·{" "}
                              </>
                            ) : null}
                            {versionMeta(current)}
                          </p>
                        </div>
                        <div className="flex shrink-0 items-center gap-2">
                          {!current.is_production ? (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() =>
                                setPromoteVersionId(current.model.id)
                              }
                            >
                              Promote to production
                            </Button>
                          ) : null}
                          <DownloadAdapterDialog
                            version={current}
                            trigger={
                              <Button variant="outline" size="sm">
                                Download
                              </Button>
                            }
                          />
                          <UseModelDialog
                            version={current}
                            {...(current.is_production
                              ? { modelId: task.slug }
                              : {})}
                            currentModel={currentModelFor(current)}
                            trigger={<Button size="sm">Use</Button>}
                          />
                        </div>
                      </div>
                      <div className="border-t px-5 py-5">
                        <EvaluationPanel
                          summary={current.summary}
                          onViewResults={() =>
                            setResultsVersionId(current.model.id)
                          }
                        />
                      </div>
                    </section>
                    {otherVersions.length ? (
                      <section>
                        <h2 className="mb-2 text-sm font-medium">
                          Other versions
                        </h2>
                        <div className="overflow-hidden rounded-lg border bg-card">
                          {otherVersions
                            .slice(0, versionsShown)
                            .map(previousRow)}
                        </div>
                        {otherVersions.length > versionsShown ? (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="mt-2"
                            onClick={() =>
                              setVersionsShown((n) => n + VERSIONS_PAGE)
                            }
                          >
                            Show{" "}
                            {Math.min(
                              VERSIONS_PAGE,
                              otherVersions.length - versionsShown,
                            )}{" "}
                            more
                          </Button>
                        ) : null}
                      </section>
                    ) : null}
                  </>
                ) : (
                  <div className="flex min-h-48 flex-col items-center justify-center rounded-lg border bg-card px-6 text-center">
                    <FlaskConical className="size-5 text-muted-foreground" />
                    <h3 className="mt-3 font-medium">No model yet</h3>
                    {activeRun ? (
                      <Button
                        variant="link"
                        size="sm"
                        className="mt-1"
                        onClick={() => setTab("runs")}
                      >
                        First training run:{" "}
                        {STAGE_LABEL[activeRun.stage].toLowerCase()} →
                      </Button>
                    ) : (
                      <ProgressRow
                        label="First training"
                        value={usableSinceLastRun}
                      />
                    )}
                  </div>
                )}
                <TrafficChart
                  task={task}
                  stats={taskStats}
                  versions={versions}
                  traces={traces}
                />
              </div>
            </TabsContent>

            {/* -------------------------------------------------------- Training runs */}
            <TabsContent value="runs">
              {runs.length ? (
                <div className="grid gap-5 lg:grid-cols-[280px_minmax(0,1fr)]">
                  <section className="self-start overflow-hidden rounded-lg border bg-card">
                    {!activeRun ? (
                      <div className="border-b border-dashed p-4">
                        <ProgressRow
                          label="Next re-train"
                          value={usableSinceLastRun}
                          compact
                        />
                      </div>
                    ) : null}
                    {runs.map((run) => {
                      const version = versions.find((v) => v.run.id === run.id);
                      return (
                        <button
                          key={run.id}
                          type="button"
                          onClick={() => setSelectedRunId(run.id)}
                          className={`block w-full border-b p-4 text-left last:border-b-0 hover:bg-muted/40 ${selectedRun?.id === run.id ? "bg-muted/60" : ""}`}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="flex items-center gap-1.5 text-sm font-medium">
                              {formatDate(run.created_at)}
                              {run.trigger === "manual" ? (
                                <span className="rounded border px-1 py-px text-[10px] font-normal text-muted-foreground">
                                  manual
                                </span>
                              ) : null}
                            </span>
                            <Badge
                              variant="outline"
                              className={stageBadgeClass(run.stage)}
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
                            {run.dataset
                              ? `${run.dataset.usable.toLocaleString()} traces`
                              : null}
                          </p>
                        </button>
                      );
                    })}
                  </section>
                  <Card className="self-start shadow-sm">
                    <CardContent className="p-5">
                      {selectedRunVersion ? (
                        <div className="mb-6 border-b pb-5">
                          <div className="mb-4 flex items-center justify-between gap-3">
                            <span className="font-mono text-sm font-semibold">
                              {selectedRunVersion.model.id}
                            </span>
                            <div className="flex items-center gap-2">
                              <DownloadAdapterDialog
                                version={selectedRunVersion}
                                trigger={
                                  <Button variant="outline" size="sm">
                                    Download
                                  </Button>
                                }
                              />
                              <UseModelDialog
                                version={selectedRunVersion}
                                currentModel={currentModelFor(
                                  selectedRunVersion,
                                )}
                                trigger={<Button size="sm">Use</Button>}
                              />
                            </div>
                          </div>
                          <EvaluationPanel
                            summary={selectedRunVersion.summary}
                            onViewResults={() =>
                              setResultsVersionId(selectedRunVersion.model.id)
                            }
                          />
                        </div>
                      ) : null}
                      {selectedRun ? (
                        <StageTimeline
                          run={selectedRun}
                          events={run_logs[selectedRun.id] ?? []}
                          onCancel={() => cancelRun(selectedRun.id)}
                        />
                      ) : null}
                    </CardContent>
                  </Card>
                </div>
              ) : (
                <div className="flex min-h-48 flex-col items-center justify-center rounded-lg border bg-card px-6 text-center">
                  <h3 className="font-medium">No training runs yet</h3>
                  <ProgressRow
                    label="First training"
                    value={usableSinceLastRun}
                  />
                </div>
              )}
            </TabsContent>

            {/* ---------------------------------------------------------------- Traces */}
            <TabsContent value="traces">
              <p className="mb-3 text-sm text-muted-foreground">
                Sampled from your production traffic, these are used to
                fine-tune a model.
              </p>
              <section className="overflow-hidden rounded-lg border bg-card">
                {summaries.length ? (
                  <Table>
                    <TableHeader className="bg-muted/40">
                      <TableRow className="hover:bg-transparent">
                        <TableHead className="h-11 pl-5">Trace</TableHead>
                        <TableHead className="h-11 px-4">Started</TableHead>
                        <TableHead className="h-11 px-4 text-right">
                          Generations
                        </TableHead>
                        <TableHead className="h-11 px-4 text-right">
                          Duration
                        </TableHead>
                        <TableHead className="h-11 pr-5 text-right">
                          Cost
                        </TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {summaries.slice(0, tracesShown).map((trace) => (
                        <TableRow
                          key={trace.trace_id}
                          className="cursor-pointer"
                          onClick={() => setSelectedTraceId(trace.trace_id)}
                        >
                          <TableCell className="h-14 pl-5 font-mono text-xs">
                            {trace.trace_id}
                          </TableCell>
                          <TableCell className="px-4 text-muted-foreground">
                            {formatTime(trace.started_at)}
                          </TableCell>
                          <TableCell className="px-4 text-right tabular-nums">
                            {trace.generation_count}
                          </TableCell>
                          <TableCell className="px-4 text-right text-muted-foreground tabular-nums">
                            {formatDuration(trace.duration_ms)}
                          </TableCell>
                          <TableCell className="pr-5 text-right text-muted-foreground tabular-nums">
                            {formatNano(trace.cost_nano_usd)}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                ) : (
                  <div className="flex min-h-48 flex-col items-center justify-center px-6 text-center">
                    <h3 className="font-medium">No traces yet</h3>
                    <p className="mt-1 text-sm text-muted-foreground">
                      Turn on trace capture in Settings.
                    </p>
                  </div>
                )}
              </section>
              {summaries.length > tracesShown ? (
                <Button
                  variant="ghost"
                  size="sm"
                  className="mt-2"
                  onClick={() => setTracesShown((n) => n + TRACES_PAGE)}
                >
                  Show more
                </Button>
              ) : null}
            </TabsContent>

            {/* -------------------------------------------------------------- Settings */}
            <TabsContent value="settings">
              <div className="max-w-2xl divide-y rounded-lg border bg-card">
                <div className="flex items-start justify-between gap-6 p-5">
                  <div>
                    <p className="text-sm font-medium">Comparison model</p>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">
                      New versions are judged, costed and timed against this.
                    </p>
                  </div>
                  <Select
                    value={task.comparison_model_id}
                    onValueChange={(v) => setTaskComparisonModel(task.id, v)}
                  >
                    <SelectTrigger className="w-64 font-mono text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {comparisonOptions.map((m) => (
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
                    <p className="text-sm font-medium">Base model</p>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">
                      The next version trains on this. Existing versions are
                      unaffected.
                    </p>
                  </div>
                  <Select
                    value={task.base_model_id}
                    onValueChange={(v) => setTaskBaseModel(task.id, v)}
                  >
                    <SelectTrigger className="w-64 font-mono text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {trainableBases.map((m) => (
                        <SelectItem
                          key={m.id}
                          value={m.id}
                          className="font-mono text-xs"
                        >
                          {m.id}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </TabsContent>
          </Tabs>
        </div>
      </main>

      <TraceSheet
        trace={selectedTrace}
        generations={selectedTraceGenerations}
        messages={
          selectedTrace ? (conversations[selectedTrace.trace_id] ?? []) : []
        }
        open={Boolean(selectedTrace)}
        onOpenChange={(open) => !open && setSelectedTraceId(null)}
      />
      <HoldoutResultsSheet
        version={resultsVersion}
        results={holdoutResults}
        open={Boolean(resultsVersion)}
        onOpenChange={(open) => !open && setResultsVersionId(null)}
      />
      {useVersion ? (
        <UseModelDialog
          version={useVersion}
          currentModel={currentModelFor(useVersion)}
          open
          onOpenChange={(open) => !open && setUseVersionId(null)}
        />
      ) : null}
      {downloadVersion ? (
        <DownloadAdapterDialog
          version={downloadVersion}
          open
          onOpenChange={(open) => !open && setDownloadVersionId(null)}
        />
      ) : null}
      <Dialog
        open={Boolean(promoteVersion)}
        onOpenChange={(open) => !open && setPromoteVersionId(null)}
      >
        {promoteVersion ? (
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Promote to production</DialogTitle>
              <DialogDescription>
                <span className="font-mono">{task.slug}</span> will point at{" "}
                <span className="font-mono">{promoteVersion.model.id}</span>.
                Requests using the task name switch once it is loaded.
                {production ? (
                  <>
                    {" "}
                    <span className="font-mono">
                      {production.model.id}
                    </span>{" "}
                    stays callable by its exact id.
                  </>
                ) : null}
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button
                variant="outline"
                onClick={() => setPromoteVersionId(null)}
              >
                Cancel
              </Button>
              <Button
                onClick={() => {
                  promote(task.id, promoteVersion.model.id);
                  setPromoteVersionId(null);
                }}
              >
                Promote
              </Button>
            </DialogFooter>
          </DialogContent>
        ) : null}
      </Dialog>
    </>,
    task.slug,
  );
};

const ProgressRow = ({
  label,
  value,
  compact: isCompact,
}: {
  label: string;
  value: number;
  compact?: boolean;
}) => (
  <div className={isCompact ? "" : "mt-4 w-72 text-left"}>
    <div className="flex items-center justify-between text-xs text-muted-foreground">
      <span>{label}</span>
      <span className="tabular-nums">
        {value} / {TRAINING_TRACE_THRESHOLD} traces
      </span>
    </div>
    <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
      <span
        className="block h-full rounded-full bg-primary"
        style={{ width: pct(value / TRAINING_TRACE_THRESHOLD) }}
      />
    </div>
  </div>
);

// ---------------------------------------------------------------------------- Traffic

const PROVIDER_COLORS = ["#171714", "#9c988a", "#cfcbbd"];
const VERSION_COLORS = ["#6e7f31", "#b6cf5a", "#3f4a1a"];
type RangeKey = "30d" | "90d" | "180d";
type Metric = "cost" | "requests" | "tokens";
const RANGE_DAYS: Record<RangeKey, number> = {
  "30d": 30,
  "90d": 90,
  "180d": 180,
};

const hashSeed = (value: string) => {
  let h = 2166136261;
  for (let i = 0; i < value.length; i++) {
    h ^= value.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
};
const mulberry32 = (seed: number) => () => {
  seed |= 0;
  seed = (seed + 0x6d2b79f5) | 0;
  let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};

/** Daily rows per model, as the usage query over `generations` would return them (mocked). */
const buildDailyTraffic = (
  task: TaskRow,
  stats: TaskStats | undefined,
  versions: VersionView[],
  traces: TraceGenerationRow[],
  daysBack: number,
) => {
  const providerModels = [
    ...new Set(traces.filter((r) => r.task === task.slug).map((r) => r.model)),
  ].slice(0, 3);
  if (!providerModels.length) providerModels.push(task.comparison_model_id);
  const own = [...versions].sort((a, b) =>
    a.model.created_at.localeCompare(b.model.created_at),
  );
  const rand = mulberry32(hashSeed(task.id));
  const daily = Math.max(4, Math.round((stats?.requests_7d ?? 28) / 7));
  const jitter = Array.from({ length: 180 }, () => 0.75 + rand() * 0.5);
  const now = new Date();
  const rows = Array.from({ length: daysBack }, (_, i) => {
    const dayIndex = daysBack - 1 - i;
    const date = new Date(now);
    date.setDate(now.getDate() - dayIndex);
    const total = Math.round(daily * (jitter[dayIndex % 180] ?? 1));
    const row: Record<string, number | string> = {
      date: date.toISOString().slice(0, 10),
    };
    let remaining = total;
    // Adoption: each version ramps toward ~90% of traffic over ~2 weeks after it is trained; newer versions take over.
    [...own].reverse().forEach((v) => {
      const daysSince =
        (date.getTime() - new Date(v.model.created_at).getTime()) / 86_400_000;
      const share = daysSince < 0 ? 0 : Math.min(0.9, daysSince * 0.065);
      const count = Math.min(remaining, Math.round(total * share));
      row[v.model.id] = count;
      remaining -= count;
    });
    providerModels.forEach((m, idx) => {
      const isLast = idx === providerModels.length - 1;
      row[m] = isLast
        ? Math.max(
            0,
            remaining -
              providerModels
                .slice(0, -1)
                .reduce((a, k) => a + Number(row[k] ?? 0), 0),
          )
        : Math.round(
            remaining *
              (idx === 0 ? 0.8 : 0.2 / Math.max(1, providerModels.length - 1)),
          );
    });
    return row;
  });
  const series = [
    ...providerModels.map((m, i) => ({
      key: m,
      color: PROVIDER_COLORS[i] ?? "#cfcbbd",
      base: null as string | null,
    })),
    ...own.map((v, i) => ({
      key: v.model.id,
      color: VERSION_COLORS[i] ?? "#6e7f31",
      base: v.model.base_model_id,
    })),
  ];
  return { rows, series };
};

const Segmented = <T extends string>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
}) => (
  <div className="flex rounded-md bg-muted p-0.5">
    {options.map((o) => (
      <button
        key={o.value}
        type="button"
        onClick={() => onChange(o.value)}
        className={`rounded px-2.5 py-1 text-xs font-medium transition-colors ${value === o.value ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}
      >
        {o.label}
      </button>
    ))}
  </div>
);

const TrafficChart = ({
  task,
  stats,
  versions,
  traces,
}: {
  task: TaskRow;
  stats: TaskStats | undefined;
  versions: VersionView[];
  traces: TraceGenerationRow[];
}) => {
  const [range, setRange] = useState<RangeKey>("30d");
  const [metric, setMetric] = useState<Metric>("cost");
  const { rows, series } = useMemo(() => {
    const built = buildDailyTraffic(
      task,
      stats,
      versions,
      traces,
      RANGE_DAYS[range],
    );
    if (metric === "requests") return built;
    const tokensPerRequest =
      (stats?.tokens_7d ?? 200) / Math.max(1, stats?.requests_7d ?? 1);
    const rows = built.rows.map((row) => {
      const out: Record<string, number | string> = { date: String(row.date) };
      built.series.forEach((s) => {
        const tokens = Number(row[s.key] ?? 0) * tokensPerRequest;
        if (metric === "tokens") out[s.key] = Math.round(tokens);
        else {
          const [inP, outP] = priceForModel(s.key, s.base ?? undefined);
          out[s.key] = Number(
            ((tokens * 0.75 * inP + tokens * 0.25 * outP) / 1_000_000).toFixed(
              5,
            ),
          );
        }
      });
      return out;
    });
    return { rows, series: built.series };
  }, [task, stats, versions, traces, range, metric]);
  const chartConfig = Object.fromEntries(
    series.map((s) => [s.key, { label: s.key, color: s.color }]),
  ) satisfies ChartConfig;
  const format = (v: number) =>
    metric === "cost"
      ? v > 0 && v < 0.1
        ? `$${v.toFixed(3)}`
        : formatUsd(v)
      : compact(v);

  return (
    <section>
      <h2 className="mb-2 text-sm font-medium">Traffic</h2>
      <Card className="shadow-sm">
        <CardHeader className="flex-row items-center justify-between gap-4 border-b p-4">
          <Segmented
            value={metric}
            onChange={setMetric}
            options={[
              { value: "cost", label: "Cost" },
              { value: "requests", label: "Requests" },
              { value: "tokens", label: "Tokens" },
            ]}
          />
          <Segmented
            value={range}
            onChange={setRange}
            options={[
              { value: "30d", label: "30d" },
              { value: "90d", label: "90d" },
              { value: "180d", label: "180d" },
            ]}
          />
        </CardHeader>
        <CardContent className="p-5">
          <ChartContainer config={chartConfig} className="h-[240px] w-full">
            <BarChart
              data={rows}
              margin={{ left: 4, right: 8, top: 12 }}
              barCategoryGap={range === "30d" ? 3 : 1}
            >
              <CartesianGrid vertical={false} />
              <XAxis
                dataKey="date"
                axisLine={false}
                tickLine={false}
                minTickGap={32}
                tickFormatter={dayLabel}
              />
              <YAxis
                axisLine={false}
                tickLine={false}
                width={52}
                tickFormatter={(v: number) => format(v)}
              />
              <ChartTooltip
                content={
                  <ChartTooltipContent
                    labelFormatter={(label) => dayLabel(String(label))}
                    valueFormatter={(v) => format(Number(v))}
                  />
                }
              />
              {series.map((s, i) => (
                <Bar
                  key={s.key}
                  dataKey={s.key}
                  stackId="traffic"
                  fill={s.color}
                  radius={i === series.length - 1 ? [3, 3, 0, 0] : 0}
                />
              ))}
            </BarChart>
          </ChartContainer>
        </CardContent>
      </Card>
    </section>
  );
};
