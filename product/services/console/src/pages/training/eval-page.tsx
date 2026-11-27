import { useParams } from "@tanstack/react-router";
import { useState } from "react";

import { OptionSelect } from "@/components/option-select";
import { EvalSummaryTable } from "@/components/training/eval-summary-table";
import { EvalStatusBadge } from "@/components/training/status-badge";
import {
  BackLink,
  DetailList,
  SectionCard,
  SkeletonRows,
  TableCard,
} from "@/components/training/training-ui";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useEval, useEvalFailures } from "@/hooks/use-grad";
import { useProductContext } from "@/hooks/use-product-context";
import { formatCost, formatCount, formatDateTime } from "@/lib/grad/format";
import { isTerminalEval } from "@/lib/grad/labels";
import { recordPreview } from "@/lib/grad/records";
import type { EvalRun } from "@/lib/grad/types";
import { ConsolePage, LoadFailed } from "@/pages/console-page";

const back = <BackLink to="/training/evals">Evals</BackLink>;

export const EvalPage = () => {
  const { workspaceId } = useProductContext();
  const { evalId } = useParams({ from: "/training/evals/$evalId" });

  return <EvalPageBody key={`${workspaceId}:${evalId}`} id={evalId} />;
};

const EvalPageBody = ({ id }: { id: string }) => {
  const evaluation = useEval(id);

  if (evaluation.isPending) {
    return (
      <ConsolePage page="training" title="Eval" width="wide" back={back}>
        <div role="status" aria-label="Loading eval" className="space-y-5">
          <Skeleton className="h-40 w-full rounded-xl" />
          <Skeleton className="h-64 w-full rounded-xl" />
        </div>
      </ConsolePage>
    );
  }

  if (evaluation.isError) {
    return (
      <ConsolePage page="training" title="Eval" width="wide" back={back}>
        <LoadFailed
          subject="this eval"
          retrying={evaluation.isFetching}
          onRetry={() => void evaluation.refetch()}
          className="rounded-xl border bg-card"
        />
      </ConsolePage>
    );
  }

  return <EvalDetail evaluation={evaluation.data} />;
};

const ALL_MODELS = "all";

const EvalDetail = ({ evaluation }: { evaluation: EvalRun }) => {
  const [model, setModel] = useState(ALL_MODELS);
  const done = evaluation.status === "completed";
  const failures = useEvalFailures(
    evaluation.id,
    model === ALL_MODELS ? undefined : model,
    done,
  );
  const progress = evaluation.progress;
  const generated = progress.totalOutputs
    ? Math.round((progress.generated / progress.totalOutputs) * 100)
    : 0;

  return (
    <ConsolePage
      page="training"
      title={evaluation.name}
      width="wide"
      back={back}
      description={
        <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <EvalStatusBadge status={evaluation.status} />
          <span>
            {evaluation.taskSource.dataset} v{evaluation.taskSource.version}
          </span>
          <span aria-hidden="true">·</span>
          <span>{formatCost(evaluation.totalCostUsd)}</span>
          <span aria-hidden="true">·</span>
          <span>Created {formatDateTime(evaluation.createdAt)}</span>
        </span>
      }
    >
      <div className="space-y-5">
        {!isTerminalEval(evaluation.status) ? (
          <SectionCard title="Progress">
            <div
              className="h-1.5 overflow-hidden rounded-full bg-muted"
              role="progressbar"
              aria-label="Outputs generated"
              aria-valuemin={0}
              aria-valuemax={progress.totalOutputs}
              aria-valuenow={progress.generated}
            >
              <span
                className="block h-full bg-foreground/80"
                style={{ width: `${generated}%` }}
              />
            </div>
            <p className="mt-3 text-sm text-muted-foreground tabular-nums">
              {formatCount(progress.generated)} of{" "}
              {formatCount(progress.totalOutputs)} outputs generated
              {progress.pendingLocalScores
                ? ` · ${formatCount(progress.pendingLocalScores)} waiting for local scores`
                : ""}
            </p>
          </SectionCard>
        ) : null}

        {evaluation.error ? (
          <p className="rounded-xl border border-destructive/30 bg-card p-5 text-sm text-destructive">
            {evaluation.error}
          </p>
        ) : null}

        {evaluation.summary.length ? (
          <EvalSummaryTable
            summaries={evaluation.summary}
            baseline={evaluation.baseline}
          />
        ) : null}

        <SectionCard title="Setup">
          <DetailList
            items={[
              { label: "Samples per task", value: evaluation.samples },
              { label: "Temperature", value: evaluation.temperature },
              { label: "Max tokens", value: formatCount(evaluation.maxTokens) },
              { label: "Pass threshold", value: evaluation.passThreshold },
              {
                label: "Judges",
                value: evaluation.judgeModels.length
                  ? evaluation.judgeModels.join(", ")
                  : "None",
              },
              { label: "Rubric items", value: evaluation.rubric.length },
            ]}
          />
          {evaluation.rubric.length ? (
            <ul className="mt-4 flex flex-wrap gap-1.5">
              {evaluation.rubric.map((item) => (
                <li key={item.name}>
                  <Badge variant="secondary" className="font-normal">
                    {item.name} · {item.kind}
                    {item.weight !== undefined ? ` · ×${item.weight}` : ""}
                  </Badge>
                </li>
              ))}
            </ul>
          ) : null}
        </SectionCard>

        {done && evaluation.mode === "eval" ? (
          <section aria-label="Failures" className="space-y-3">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 className="text-base font-semibold">Failures</h2>
                <p className="text-sm text-muted-foreground">
                  Tasks that scored below the pass threshold of{" "}
                  {evaluation.passThreshold}.
                </p>
              </div>
              <OptionSelect
                label="Model"
                value={model}
                options={[
                  { value: ALL_MODELS, label: "All models" },
                  ...evaluation.models.map((name) => ({
                    value: name,
                    label: name,
                  })),
                ]}
                onValueChange={setModel}
                className="min-w-48 bg-card"
              />
            </div>
            {failures.isError ? (
              <LoadFailed
                subject="failures"
                retrying={failures.isFetching}
                onRetry={() => void failures.refetch()}
                className="rounded-xl border bg-card"
              />
            ) : !failures.isPending && !failures.data.length ? (
              <p className="rounded-xl border bg-card p-5 text-sm text-muted-foreground">
                No failures.
              </p>
            ) : (
              <TableCard label="Failed tasks" busy={failures.isPending}>
                <Table>
                  <TableHeader className="bg-muted/40">
                    <TableRow className="hover:bg-transparent">
                      <TableHead className="h-11 pl-5">Task</TableHead>
                      <TableHead className="h-11">Model</TableHead>
                      <TableHead className="h-11">Input</TableHead>
                      <TableHead className="h-11 text-right">Score</TableHead>
                      <TableHead className="h-11 pr-5">Samples</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {failures.isPending ? (
                      <SkeletonRows columns={5} rows={3} />
                    ) : null}
                    {(failures.data ?? []).map((outcome) => (
                      <TableRow
                        key={`${outcome.taskId}-${outcome.model}`}
                        className="align-top"
                      >
                        <TableCell className="py-3 pl-5 font-mono text-xs">
                          {outcome.taskId}
                        </TableCell>
                        <TableCell className="py-3 font-mono text-xs text-muted-foreground">
                          {outcome.model}
                        </TableCell>
                        <TableCell className="max-w-md py-3 whitespace-normal">
                          <p className="line-clamp-3 text-sm">
                            {recordPreview(outcome.record).input || "—"}
                          </p>
                        </TableCell>
                        <TableCell className="py-3 text-right text-destructive tabular-nums">
                          {outcome.score.toFixed(2)}
                        </TableCell>
                        <TableCell className="py-3 pr-5 font-mono text-xs text-muted-foreground">
                          {outcome.sampleScores
                            .map((score) => score.toFixed(2))
                            .join(" ")}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableCard>
            )}
          </section>
        ) : null}
      </div>
    </ConsolePage>
  );
};
