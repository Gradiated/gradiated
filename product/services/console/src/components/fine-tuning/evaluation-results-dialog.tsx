import { formatNanoUsd } from "@/lib/format";
import { modelDisplayName } from "@gradiated/contracts/model-catalog";
import { useQuery } from "@tanstack/react-query";
import { getEvaluationResults } from "@/api/training";
import { useProductContext } from "@/hooks/use-product-context";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { QueryState } from "./query-state";
import type { VersionView } from "@/store/fine-tuning-types";

export const EvaluationResultsDialog = ({
  version,
  onClose,
}: {
  version: VersionView;
  onClose: () => void;
}) => {
  const { workspaceId } = useProductContext();
  const query = useQuery({
    queryKey: ["evaluation-results", workspaceId, version.id],
    queryFn: ({ signal }) =>
      getEvaluationResults(workspaceId, version.task, version.id, signal),
    gcTime: 0,
    retry: 1,
  });

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-4xl">
        <DialogHeader>
          <DialogTitle>Test results</DialogTitle>
          <DialogDescription>
            {version.name} compared with{" "}
            <code className="rounded bg-muted px-1 py-0.5 font-mono text-[0.9em]">
              {modelDisplayName(version.summary?.comparison_model_id)}
            </code>
            . Held-out responses judged by{" "}
            <code className="rounded bg-muted px-1 py-0.5 font-mono text-[0.9em]">
              {modelDisplayName(version.summary?.judge_model_id)}
            </code>
            .
          </DialogDescription>
        </DialogHeader>
        <QueryState query={query} />
        {query.data?.map((row, index) => {
          const judgments = "judgment" in row ? [row.judgment] : row.judgments;
          const decision =
            "judgment" in row
              ? row.judgment === "TIE"
                ? "Equivalent"
                : row.judgment === "A" || row.judgment === "B"
                  ? (row.judgment === "A") === row.fine_tuned_first
                    ? "Better"
                    : "Worse"
                  : "Unresolved"
              : judgments[0] === "A" && judgments[1] === "B"
                ? "Better"
                : judgments[0] === "B" && judgments[1] === "A"
                  ? "Worse"
                  : judgments.every((value) => value === "TIE")
                    ? "Equivalent"
                    : "Unresolved";

          return (
            <section key={row.id} className="space-y-3 rounded-lg border p-4">
              <div className="flex justify-between gap-3 text-sm font-medium">
                <h3>Example {index + 1}</h3>
                <span>{decision}</span>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                {(["fine_tuned", "comparison"] as const).map((arm) => (
                  <div key={arm} className="min-w-0 space-y-2">
                    <h4 className="text-sm font-medium">
                      {arm === "fine_tuned"
                        ? version.name
                        : modelDisplayName(
                            version.summary?.comparison_model_id,
                          )}
                    </h4>
                    <pre className="ph-no-capture max-h-64 overflow-auto rounded-md bg-muted p-3 text-xs whitespace-pre-wrap break-words">
                      {row[arm].text}
                    </pre>
                    <p className="text-xs text-muted-foreground">
                      {row[arm].tokens} output tokens ·{" "}
                      {row[arm].seconds.toFixed(2)}s
                      {row[arm].cost_nano_usd !== undefined
                        ? ` · ${formatNanoUsd(row[arm].cost_nano_usd)}`
                        : null}
                    </p>
                  </div>
                ))}
              </div>
              <p className="text-xs text-muted-foreground">
                Judge decision{judgments.length > 1 ? "s" : ""}:{" "}
                {judgments.join(", ")}
              </p>
            </section>
          );
        })}
      </DialogContent>
    </Dialog>
  );
};
