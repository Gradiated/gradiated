import { CircleAlert } from "lucide-react";

import { SectionCard, DetailList } from "@/components/training/training-ui";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  evalReportRows,
  formatMetric,
  formatShare,
  selectionMetric,
} from "@/lib/grad/eval-report";
import { formatCost, formatCount } from "@/lib/grad/format";
import { RECIPE_LABEL } from "@/lib/grad/labels";
import type {
  CheckpointEvalResult,
  EvalReport,
  RecipeKind,
} from "@/lib/grad/types";

export const EvalReportCard = ({
  kind,
  report,
  checkpointEvals,
}: {
  kind: RecipeKind;
  report: EvalReport | null;
  checkpointEvals: readonly CheckpointEvalResult[];
}) => {
  if (!report) {
    return (
      <SectionCard
        title="Eval report"
        description={`${RECIPE_LABEL[kind]} recipe`}
      >
        <p className="text-sm text-muted-foreground">
          The report is written when the run completes.
        </p>
      </SectionCard>
    );
  }

  const headline = selectionMetric(report);
  const rows = evalReportRows(kind, report);

  return (
    <SectionCard
      title="Eval report"
      description={`${RECIPE_LABEL[kind]} recipe · ${formatCount(report.trainRecords)} train and ${formatCount(report.evalRecords)} held-out records`}
    >
      <div className="flex flex-wrap items-end gap-x-8 gap-y-3">
        <div>
          <p className="text-xs text-muted-foreground">
            {headline.name} (
            {headline.mode === "min" ? "lower is better" : "higher is better"})
          </p>
          <p className="mt-1 text-3xl font-semibold tracking-[-0.035em] tabular-nums">
            {headline.value === null
              ? "—"
              : headline.share
                ? formatShare(headline.value)
                : formatMetric(headline.value)}
          </p>
        </div>
        <p className="pb-1 text-sm text-muted-foreground">
          Selected step {formatCount(report.selectedStep)}
          {report.bestStep !== null && report.bestStep !== report.selectedStep
            ? ` · best ${formatCount(report.bestStep)}`
            : ""}{" "}
          · final {formatCount(report.finalStep)}
        </p>
      </div>

      {rows.length ? <DetailList className="mt-5" items={rows} /> : null}

      {report.warnings.length ? (
        <ul className="mt-5 space-y-2">
          {report.warnings.map((warning) => (
            <li key={warning} className="flex gap-2 text-sm text-[#9a6a00]">
              <CircleAlert className="mt-0.5 size-4 shrink-0" />
              {warning}
            </li>
          ))}
        </ul>
      ) : null}

      {checkpointEvals.length ? (
        <div className="mt-5 overflow-x-auto rounded-lg border">
          <Table>
            <TableHeader className="bg-muted/40">
              <TableRow className="hover:bg-transparent">
                <TableHead className="pl-4">Checkpoint eval</TableHead>
                <TableHead>Step</TableHead>
                <TableHead>Dataset</TableHead>
                <TableHead>Score</TableHead>
                <TableHead className="pr-4">Cost</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {checkpointEvals.map((result) => (
                <TableRow key={`${result.name}-${result.step}`}>
                  <TableCell className="pl-4 font-medium">
                    {result.name}
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {formatCount(result.step)}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {result.dataset} v{result.datasetVersion}
                  </TableCell>
                  <TableCell className="tabular-nums">
                    {result.score === null
                      ? (result.error ?? result.status)
                      : formatMetric(result.score)}
                  </TableCell>
                  <TableCell className="pr-4 tabular-nums text-muted-foreground">
                    {formatCost(result.costUsd)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : null}
    </SectionCard>
  );
};
