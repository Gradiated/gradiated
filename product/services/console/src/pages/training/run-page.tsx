import { Link, useParams } from "@tanstack/react-router";
import { CircleStop, LoaderCircle, Play, RefreshCw } from "lucide-react";
import { useId, useMemo, useState } from "react";

import { ArtifactCard } from "@/components/training/artifact-card";
import { CheckpointsTable } from "@/components/training/checkpoints-table";
import { EvalReportCard } from "@/components/training/eval-report-card";
import { EvalChart, LossChart } from "@/components/training/run-charts";
import { RunProgress } from "@/components/training/run-progress";
import { RunTimeline } from "@/components/training/run-timeline";
import { RunStatusBadge } from "@/components/training/status-badge";
import { BackLink, Stat, StatGrid } from "@/components/training/training-ui";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useArtifact,
  useCheckpoints,
  useRun,
  useRunActions,
} from "@/hooks/use-grad";
import { useProductContext } from "@/hooks/use-product-context";
import { useRunEvents, type RunEventsState } from "@/hooks/use-run-events";
import { formatMetric } from "@/lib/grad/eval-report";
import { formatCost, formatDateTime, formatTokens } from "@/lib/grad/format";
import { canResumeRun, isTerminalRun, RECIPE_LABEL } from "@/lib/grad/labels";
import { lossSeries } from "@/lib/grad/run-events";
import type { Run } from "@/lib/grad/types";
import { canManageOrganization } from "@/lib/roles";
import { ConsolePage, LoadFailed } from "@/pages/console-page";

export const RunPage = () => {
  const { workspaceId } = useProductContext();
  const { runId } = useParams({ from: "/_training/training/runs/$runId" });

  return <RunPageBody key={`${workspaceId}:${runId}`} runId={runId} />;
};

const back = <BackLink to="/training/runs">Training runs</BackLink>;

const RunPageBody = ({ runId }: { runId: string }) => {
  const run = useRun(runId);

  if (run.isPending) {
    return (
      <ConsolePage
        page="training"
        title="Training run"
        width="wide"
        back={back}
      >
        <div role="status" aria-label="Loading run" className="space-y-5">
          <Skeleton className="h-36 w-full rounded-xl" />
          <Skeleton className="h-24 w-full rounded-xl" />
          <Skeleton className="h-72 w-full rounded-xl" />
        </div>
      </ConsolePage>
    );
  }

  if (run.isError) {
    return (
      <ConsolePage
        page="training"
        title="Training run"
        width="wide"
        back={back}
      >
        <LoadFailed
          subject="this run"
          retrying={run.isFetching}
          onRetry={() => void run.refetch()}
          className="rounded-xl border bg-card"
        />
      </ConsolePage>
    );
  }

  return <RunDetail run={run.data} />;
};

const LiveIndicator = ({
  state,
  onRetry,
}: {
  state: RunEventsState;
  onRetry: () => void;
}) =>
  state === "failed" ? (
    <Button variant="outline" size="sm" onClick={onRetry}>
      <RefreshCw />
      Reconnect
    </Button>
  ) : state === "live" || state === "connecting" ? (
    <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
      <span className="size-1.5 rounded-full bg-[#7a9a1f] ring-2 ring-[#7a9a1f]/25" />
      {state === "live" ? "Live" : "Connecting"}
    </span>
  ) : null;

const RunDetail = ({ run }: { run: Run }) => {
  const { selectedOrganization } = useProductContext();
  const stream = useRunEvents(run.id);
  const checkpoints = useCheckpoints(run.id);
  const artifact = useArtifact(run.artifactId);
  const { cancel, resume } = useRunActions(run.id);
  const [resumeOpen, setResumeOpen] = useState(false);
  const series = useMemo(() => lossSeries(stream.events), [stream.events]);
  const metric = run.latestMetric;
  const trainLoss = series.at(-1)?.loss ?? metric?.loss;
  const evalLoss =
    series.findLast((point) => point.evalLoss !== undefined)?.evalLoss ??
    metric?.evalLoss;

  return (
    <ConsolePage
      page="training"
      title={run.name}
      width="wide"
      back={back}
      description={
        <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <RunStatusBadge status={run.status} />
          <span>{RECIPE_LABEL[run.recipeKind]}</span>
          <span aria-hidden="true">·</span>
          <code className="font-mono text-xs">{run.resolvedConfig.model}</code>
          <span aria-hidden="true">·</span>
          <Link
            to="/training/datasets/$datasetName"
            params={{ datasetName: run.datasetName }}
            className="underline-offset-4 hover:underline"
          >
            {run.datasetName} v{run.datasetVersion}
          </Link>
          <span aria-hidden="true">·</span>
          <span>Created {formatDateTime(run.createdAt)}</span>
        </span>
      }
      actions={
        <>
          {!isTerminalRun(run.status) ? (
            <Button
              variant="outline"
              disabled={cancel.isPending}
              onClick={() => cancel.mutate()}
            >
              {cancel.isPending ? (
                <LoaderCircle className="animate-spin" />
              ) : (
                <CircleStop />
              )}
              Cancel run
            </Button>
          ) : null}
          {canResumeRun(run.status) ? (
            <Button
              variant="outline"
              disabled={resume.isPending}
              onClick={() =>
                run.status === "stopped_budget"
                  ? setResumeOpen(true)
                  : resume.mutate(undefined, { onSuccess: stream.retry })
              }
            >
              {resume.isPending ? (
                <LoaderCircle className="animate-spin" />
              ) : (
                <Play />
              )}
              Resume
            </Button>
          ) : null}
        </>
      }
    >
      <div className="space-y-5">
        <RunProgress run={run} />

        <StatGrid>
          <Stat
            label="Train loss"
            value={trainLoss === undefined ? "—" : formatMetric(trainLoss)}
          />
          <Stat
            label="Eval loss"
            value={evalLoss == null ? "—" : formatMetric(evalLoss)}
          />
          <Stat
            label="Tokens"
            value={formatTokens(run.tokensProcessed)}
            detail={`${formatCost(run.pricePerMillionTokens)} per million`}
          />
          <Stat
            label="Cost"
            value={formatCost(run.costUsd)}
            detail={
              run.maxCostUsd === null
                ? "No cost cap"
                : `Cap ${formatCost(run.maxCostUsd)}`
            }
          />
        </StatGrid>

        <div className="grid gap-5 lg:grid-cols-2">
          <LossChart events={stream.events} />
          <EvalChart events={stream.events} />
        </div>

        <div className="grid gap-5 lg:grid-cols-[minmax(0,1.4fr)_minmax(320px,1fr)]">
          <div className="min-w-0 space-y-5">
            <EvalReportCard
              kind={run.recipeKind}
              report={run.evalReport}
              checkpointEvals={run.checkpointEvals}
            />
            <ArtifactCard
              artifact={artifact.data}
              loading={Boolean(run.artifactId) && artifact.isPending}
              canDeploy={canManageOrganization(selectedOrganization)}
            />
            <CheckpointsTable
              checkpoints={checkpoints.data ?? []}
              loading={checkpoints.isPending}
            />
          </div>
          <RunTimeline
            events={stream.events}
            live={<LiveIndicator state={stream.state} onRetry={stream.retry} />}
          />
        </div>
        {stream.state === "failed" ? (
          <p className="text-sm text-muted-foreground">
            Live updates stopped: {stream.error?.message}
          </p>
        ) : null}
      </div>

      {resumeOpen ? (
        <ResumeDialog
          run={run}
          pending={resume.isPending}
          onClose={() => setResumeOpen(false)}
          onResume={(maxCostUsd) =>
            resume.mutate(maxCostUsd, {
              onSuccess: () => {
                setResumeOpen(false);
                stream.retry();
              },
            })
          }
        />
      ) : null}
    </ConsolePage>
  );
};

const ResumeDialog = ({
  run,
  pending,
  onClose,
  onResume,
}: {
  run: Run;
  pending: boolean;
  onClose: () => void;
  onResume: (maxCostUsd: number) => void;
}) => {
  const id = useId();
  const [cap, setCap] = useState(String((run.maxCostUsd ?? run.costUsd) * 2));
  const value = Number(cap);
  const valid = Number.isFinite(value) && value > run.costUsd;

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <form
          className="space-y-5"
          onSubmit={(event) => {
            event.preventDefault();
            if (valid) onResume(value);
          }}
        >
          <DialogHeader>
            <DialogTitle>Resume with a higher cost cap</DialogTitle>
            <DialogDescription>
              The run stopped at its {formatCost(run.maxCostUsd ?? 0)} cap after
              spending {formatCost(run.costUsd)}. It resumes from its latest
              checkpoint.
            </DialogDescription>
          </DialogHeader>
          <Field>
            <FieldLabel htmlFor={id}>New cost cap (USD)</FieldLabel>
            <Input
              id={id}
              inputMode="decimal"
              value={cap}
              onChange={(event) => setCap(event.target.value)}
            />
          </Field>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={!valid || pending}>
              {pending ? <LoaderCircle className="animate-spin" /> : null}
              Resume run
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};
