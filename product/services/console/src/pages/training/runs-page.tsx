import { Link, useNavigate } from "@tanstack/react-router";
import { FlaskConical, Plus } from "lucide-react";

import { RunStatusBadge } from "@/components/training/status-badge";
import {
  EmptyState,
  LoadMore,
  SkeletonRows,
  TableCard,
} from "@/components/training/training-ui";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useRuns } from "@/hooks/use-grad";
import { useProductContext } from "@/hooks/use-product-context";
import { formatCost, formatCount, formatDateTime } from "@/lib/grad/format";
import { isTerminalRun, PHASE_LABEL, RECIPE_LABEL } from "@/lib/grad/labels";
import type { Run } from "@/lib/grad/types";
import { ConsolePage, LoadFailed } from "@/pages/console-page";

const NewRunButton = () => (
  <Button asChild>
    <Link to="/training/runs/new">
      <Plus />
      New run
    </Link>
  </Button>
);

export const RunsPage = () => {
  const { workspaceId } = useProductContext();

  return <RunsPageBody key={workspaceId} />;
};

const RunsPageBody = () => {
  const runs = useRuns();
  const rows = runs.data?.pages.flatMap((page) => page.data) ?? [];

  return (
    <ConsolePage
      page="training"
      title="Training runs"
      description="Fine-tune models on your datasets. Runs report live progress and keep their checkpoints and artifacts."
      width="wide"
      actions={<NewRunButton />}
    >
      {runs.isError ? (
        <LoadFailed
          subject="training runs"
          retrying={runs.isFetching}
          onRetry={() => void runs.refetch()}
          className="rounded-xl border bg-card"
        />
      ) : !runs.isPending && !rows.length ? (
        <EmptyState
          icon={<FlaskConical />}
          title="No training runs yet"
          description="Pick a dataset and a recipe, review the cost estimate, then start a run."
          action={<NewRunButton />}
        />
      ) : (
        <TableCard
          label="Training runs"
          busy={runs.isPending}
          footer={
            <LoadMore
              hasMore={runs.hasNextPage}
              loading={runs.isFetchingNextPage}
              onLoad={() => void runs.fetchNextPage()}
            />
          }
        >
          <RunsTable runs={rows} loading={runs.isPending} />
        </TableCard>
      )}
    </ConsolePage>
  );
};

export const RunsTable = ({
  runs,
  loading,
}: {
  runs: readonly Run[];
  loading: boolean;
}) => {
  const navigate = useNavigate();

  return (
    <Table>
      <TableHeader className="bg-muted/40">
        <TableRow className="hover:bg-transparent">
          <TableHead className="h-11 pl-5">Run</TableHead>
          <TableHead className="h-11">Status</TableHead>
          <TableHead className="h-11">Recipe</TableHead>
          <TableHead className="h-11">Model</TableHead>
          <TableHead className="h-11">Dataset</TableHead>
          <TableHead className="h-11 text-right">Cost</TableHead>
          <TableHead className="h-11 pr-5">Created</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {loading ? <SkeletonRows columns={7} /> : null}
        {runs.map((run) => (
          <TableRow
            key={run.id}
            className="cursor-pointer"
            onClick={() =>
              void navigate({
                to: "/training/runs/$runId",
                params: { runId: run.id },
              })
            }
          >
            <TableCell className="h-14 pl-5">
              <Link
                to="/training/runs/$runId"
                params={{ runId: run.id }}
                onClick={(event) => event.stopPropagation()}
                className="font-medium focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
              >
                {run.name}
              </Link>
            </TableCell>
            <TableCell>
              <div className="flex flex-col items-start gap-1">
                <RunStatusBadge status={run.status} />
                {!isTerminalRun(run.status) && run.phase ? (
                  <span className="text-xs text-muted-foreground tabular-nums">
                    {PHASE_LABEL[run.phase]}
                    {run.totalSteps
                      ? ` · ${formatCount(run.currentStep)}/${formatCount(run.totalSteps)}`
                      : ""}
                  </span>
                ) : null}
              </div>
            </TableCell>
            <TableCell>{RECIPE_LABEL[run.recipeKind]}</TableCell>
            <TableCell className="max-w-56 truncate font-mono text-xs text-muted-foreground">
              {run.resolvedConfig.model}
            </TableCell>
            <TableCell className="text-muted-foreground">
              {run.datasetName}{" "}
              <span className="text-xs">v{run.datasetVersion}</span>
            </TableCell>
            <TableCell className="text-right tabular-nums">
              {formatCost(run.costUsd)}
              {run.maxCostUsd !== null ? (
                <span className="block text-xs text-muted-foreground">
                  of {formatCost(run.maxCostUsd)}
                </span>
              ) : null}
            </TableCell>
            <TableCell className="pr-5 text-muted-foreground">
              {formatDateTime(run.createdAt)}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
};
