import { toneText } from "@/components/training/status-badge";
import { TableCard } from "@/components/training/training-ui";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  deltaTone,
  formatDelta,
  formatInterval,
  passAtK,
} from "@/lib/grad/evals";
import { formatCost, formatCount, formatTokens } from "@/lib/grad/format";
import type { EvalModelSummary } from "@/lib/grad/types";
import { cn } from "@/lib/utils";

const IntervalBar = ({ summary }: { summary: EvalModelSummary }) => (
  <span
    className="relative mt-1.5 block h-1.5 w-32 rounded-full bg-muted"
    aria-hidden="true"
  >
    <span
      className="absolute inset-y-0 rounded-full bg-foreground/25"
      style={{
        left: `${Math.max(0, summary.ciLow) * 100}%`,
        width: `${Math.max(0.01, Math.min(1, summary.ciHigh) - Math.max(0, summary.ciLow)) * 100}%`,
      }}
    />
    <span
      className="absolute top-1/2 size-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-foreground"
      style={{ left: `${Math.min(1, Math.max(0, summary.overall)) * 100}%` }}
    />
  </span>
);

export const EvalSummaryTable = ({
  summaries,
  baseline,
}: {
  summaries: readonly EvalModelSummary[];
  baseline: string | null;
}) => (
  <TableCard label="Summary">
    <Table>
      <TableHeader className="bg-muted/40">
        <TableRow className="hover:bg-transparent">
          <TableHead className="h-11 pl-5">Model</TableHead>
          <TableHead className="h-11">Score (95% CI)</TableHead>
          <TableHead className="h-11">
            {baseline ? `vs ${baseline}` : "vs baseline"}
          </TableHead>
          <TableHead className="h-11">Pass@k</TableHead>
          <TableHead className="h-11 text-right">Tasks</TableHead>
          <TableHead className="h-11 text-right">Errors</TableHead>
          <TableHead className="h-11 text-right">Tokens / task</TableHead>
          <TableHead className="h-11 pr-5 text-right">
            Cost / 1k tasks
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {summaries.map((summary) => (
          <TableRow key={summary.model} className="align-top">
            <TableCell className="py-3 pl-5 font-mono text-xs font-medium">
              {summary.model}
              {summary.model === baseline ? (
                <span className="ml-2 font-sans text-xs font-normal text-muted-foreground">
                  baseline
                </span>
              ) : null}
            </TableCell>
            <TableCell className="py-3 tabular-nums">
              <span className="font-medium">{summary.overall.toFixed(3)}</span>{" "}
              <span className="text-xs text-muted-foreground">
                ({formatInterval(summary.ciLow, summary.ciHigh)})
              </span>
              <IntervalBar summary={summary} />
            </TableCell>
            <TableCell className="py-3 tabular-nums">
              {summary.vsBaseline ? (
                <span className={cn(toneText[deltaTone(summary.vsBaseline)])}>
                  {formatDelta(summary.vsBaseline.delta)}
                  <span className="block text-xs text-muted-foreground">
                    {formatInterval(
                      summary.vsBaseline.ciLow,
                      summary.vsBaseline.ciHigh,
                    )}
                  </span>
                </span>
              ) : (
                <span className="text-muted-foreground">—</span>
              )}
            </TableCell>
            <TableCell className="py-3 text-xs tabular-nums text-muted-foreground">
              {passAtK(summary)
                .map(({ k, value }) => `@${k} ${value.toFixed(2)}`)
                .join(" · ") || "—"}
            </TableCell>
            <TableCell className="py-3 text-right tabular-nums">
              {formatCount(summary.tasks)}
            </TableCell>
            <TableCell
              className={cn(
                "py-3 text-right tabular-nums",
                summary.errors ? "text-destructive" : "text-muted-foreground",
              )}
            >
              {formatCount(summary.errors)}
            </TableCell>
            <TableCell className="py-3 text-right tabular-nums text-muted-foreground">
              {formatTokens(summary.tokensPerTask)}
            </TableCell>
            <TableCell className="py-3 pr-5 text-right tabular-nums">
              {summary.costPer1kTasksUsd === null
                ? "—"
                : formatCost(summary.costPer1kTasksUsd)}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  </TableCard>
);
