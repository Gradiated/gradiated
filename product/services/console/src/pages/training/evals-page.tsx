import { Link, useNavigate } from "@tanstack/react-router";
import { ChartColumn } from "lucide-react";

import { EvalStatusBadge } from "@/components/training/status-badge";
import {
  EmptyState,
  LoadMore,
  SkeletonRows,
  TableCard,
} from "@/components/training/training-ui";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useEvals } from "@/hooks/use-grad";
import { useProductContext } from "@/hooks/use-product-context";
import { bestModel } from "@/lib/grad/evals";
import { formatCost, formatDateTime } from "@/lib/grad/format";
import { ConsolePage, LoadFailed } from "@/pages/console-page";

export const EvalsPage = () => {
  const { workspaceId } = useProductContext();

  return <EvalsPageBody key={workspaceId} />;
};

const EvalsPageBody = () => {
  const navigate = useNavigate();
  const evals = useEvals();
  const rows = evals.data?.pages.flatMap((page) => page.data) ?? [];

  return (
    <ConsolePage
      page="training"
      title="Evals"
      description="Model comparisons on a dataset, scored by judges and validators, with 95% confidence intervals."
      width="wide"
    >
      {evals.isError ? (
        <LoadFailed
          subject="evals"
          retrying={evals.isFetching}
          onRetry={() => void evals.refetch()}
          className="rounded-xl border bg-card"
        />
      ) : !evals.isPending && !rows.length ? (
        <EmptyState
          icon={<ChartColumn />}
          title="No evals yet"
          description={
            <>
              Start one with{" "}
              <code className="font-mono text-xs">grad evals create</code> or{" "}
              <code className="font-mono text-xs">grad.evals.create()</code> in
              the SDK.
            </>
          }
        />
      ) : (
        <TableCard
          label="Evals"
          busy={evals.isPending}
          footer={
            <LoadMore
              hasMore={evals.hasNextPage}
              loading={evals.isFetchingNextPage}
              onLoad={() => void evals.fetchNextPage()}
            />
          }
        >
          <Table>
            <TableHeader className="bg-muted/40">
              <TableRow className="hover:bg-transparent">
                <TableHead className="h-11 pl-5">Eval</TableHead>
                <TableHead className="h-11">Status</TableHead>
                <TableHead className="h-11">Dataset</TableHead>
                <TableHead className="h-11">Models</TableHead>
                <TableHead className="h-11">Top score</TableHead>
                <TableHead className="h-11 text-right">Cost</TableHead>
                <TableHead className="h-11 pr-5">Created</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {evals.isPending ? <SkeletonRows columns={7} /> : null}
              {rows.map((evaluation) => {
                const best = bestModel(evaluation.summary);

                return (
                  <TableRow
                    key={evaluation.id}
                    className="cursor-pointer"
                    onClick={() =>
                      void navigate({
                        to: "/training/evals/$evalId",
                        params: { evalId: evaluation.id },
                      })
                    }
                  >
                    <TableCell className="h-14 pl-5">
                      <Link
                        to="/training/evals/$evalId"
                        params={{ evalId: evaluation.id }}
                        onClick={(event) => event.stopPropagation()}
                        className="font-medium"
                      >
                        {evaluation.name}
                      </Link>
                      {evaluation.mode === "score" ? (
                        <span className="ml-2 text-xs text-muted-foreground">
                          scoring
                        </span>
                      ) : null}
                    </TableCell>
                    <TableCell>
                      <EvalStatusBadge status={evaluation.status} />
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {evaluation.taskSource.dataset}{" "}
                      <span className="text-xs">
                        v{evaluation.taskSource.version}
                      </span>
                    </TableCell>
                    <TableCell className="max-w-56 truncate font-mono text-xs text-muted-foreground">
                      {evaluation.models.join(", ")}
                    </TableCell>
                    <TableCell className="tabular-nums">
                      {best ? (
                        <>
                          {best.overall.toFixed(3)}{" "}
                          <span className="font-mono text-xs text-muted-foreground">
                            {best.model}
                          </span>
                        </>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatCost(evaluation.totalCostUsd)}
                    </TableCell>
                    <TableCell className="pr-5 text-muted-foreground">
                      {formatDateTime(evaluation.createdAt)}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </TableCard>
      )}
    </ConsolePage>
  );
};
