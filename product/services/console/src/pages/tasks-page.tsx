import { Loader2 } from "lucide-react";
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
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { formatPercent } from "@/lib/format";
import type { components } from "@/api/schema";
import { STAGE_LABEL, type JudgeOutcome } from "@/store/fine-tuning-types";
import { Link, useNavigate } from "@tanstack/react-router";
import { useState } from "react";

import { TrainingGate } from "@/components/fine-tuning/training-gate";
import { ConnectDialog } from "@/components/fine-tuning/connect-dialog";
import { ConnectSnippet } from "@/components/fine-tuning/connect-snippet";
import { SettingsCard } from "@/components/fine-tuning/settings-card";
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
import { ConsolePage } from "@/pages/console-page";
import { OptionTabs, type Option } from "@/components/option-select";
import { useProductContext } from "@/hooks/use-product-context";
import { useTasks } from "@/hooks/use-training";
import { QueryState } from "@/components/fine-tuning/query-state";
import { JudgeSettings } from "@/components/fine-tuning/judge-settings";

const TABS = [
  { value: "tasks", label: "Models" },
  { value: "settings", label: "Settings" },
] as const satisfies readonly Option<string>[];

export const TasksPage = () => (
  <TrainingGate>
    <ScopedTasksPage />
  </TrainingGate>
);

const ScopedTasksPage = () => {
  const { workspaceId } = useProductContext();

  return <TasksPageBody key={workspaceId} />;
};

const TasksPageBody = () => {
  const navigate = useNavigate();
  const query = useTasks();
  const tasks = query.data?.data ?? [];
  const [tab, setTab] = useState<(typeof TABS)[number]["value"]>("tasks");
  const [connectOpen, setConnectOpen] = useState(false);

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
          {query.isPending || query.error ? (
            <QueryState query={query} />
          ) : tasks.length ? (
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
                      key={task.name}
                      task={task}
                      onOpen={() =>
                        void navigate({
                          to: "/tasks/$taskId",
                          params: { taskId: task.name },
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
                <Loader2 className="size-4 animate-spin text-muted-foreground" />
                <span className="text-muted-foreground">
                  Waiting for your first request…
                </span>
              </div>
            </div>
          )}
        </TabsContent>

        <TabsContent value="settings">
          <SettingsCard>
            <JudgeSettings />
            <TraceCaptureSettings />
          </SettingsCard>
        </TabsContent>
      </OptionTabs>

      <ConnectDialog open={connectOpen} onOpenChange={setConnectOpen} />
    </ConsolePage>
  );
};

const trainedDate = new Intl.DateTimeFormat(undefined, {
  day: "numeric",
  month: "short",
});

const TaskRowView = ({
  task,
  onOpen,
}: {
  task: components["schemas"]["TaskListItem"];
  onOpen: () => void;
}) => {
  const run = task.latest_run;
  const summary = run?.evaluation;
  const version = run?.version_name;

  return (
    <TableRow className="cursor-pointer" onClick={onOpen}>
      <TableCell className="h-14 pl-5 font-medium">
        <Link
          to="/tasks/$taskId"
          params={{ taskId: task.name }}
          onClick={(event) => event.stopPropagation()}
          className="rounded-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        >
          {task.name}
        </Link>
      </TableCell>
      <TableCell className="px-4">
        {version ? (
          <span className="flex flex-wrap items-center gap-1.5">
            <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">
              {version}
            </code>
            {run?.version_id !== task.production_version_id ? (
              <span className="text-xs text-muted-foreground">
                not promoted
              </span>
            ) : null}
          </span>
        ) : (
          <span className="text-muted-foreground">
            {run ? STAGE_LABEL[run.stage] : "No model yet"}
          </span>
        )}
      </TableCell>
      <TableCell className="px-4">
        <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs text-muted-foreground">
          {summary?.comparison_model_id ?? task.comparison_model_id ?? "—"}
        </code>
      </TableCell>
      <TableCell className="px-4 tabular-nums">
        {summary ? (
          <RatioLabel
            ratio={costAdvantage(summary)}
            detail={costPer1kRequests(summary)}
          />
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </TableCell>
      <TableCell className="px-4 tabular-nums">
        {summary ? (
          <RatioLabel
            ratio={speedAdvantage(summary)}
            detail={outputSpeed(summary)}
          />
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </TableCell>
      <TableCell className="px-4">
        {summary ? (
          <QualityBar result={summary.vs_comparison} />
        ) : (
          <span className="text-muted-foreground tabular-nums">—</span>
        )}
      </TableCell>
      <TableCell className="pr-5 text-muted-foreground">
        {version && run?.finished_at
          ? trainedDate.format(new Date(run.finished_at))
          : "—"}
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
