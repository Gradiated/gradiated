import { Badge } from "@/components/ui/badge";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import type {
  EvaluationResultLine,
  VersionView,
} from "@/store/mock-fine-tuning";

const verdictClass: Record<EvaluationResultLine["verdict"], string> = {
  better: "border-[#cadb87] bg-[#f2f7d9] text-[#475617]",
  equivalent: "border-border bg-muted text-muted-foreground",
  worse: "border-amber-200 bg-amber-50 text-amber-800",
  unresolved: "border-border bg-transparent text-muted-foreground",
};

/** GET .../runs/{run_id}/evaluation-results, paged. */
export const HoldoutResultsSheet = ({
  version,
  results,
  open,
  onOpenChange,
}: {
  version: VersionView | null;
  results: EvaluationResultLine[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) => (
  <Sheet open={open} onOpenChange={onOpenChange}>
    <SheetContent className="w-full overflow-y-auto sm:max-w-3xl">
      {version ? (
        <>
          <SheetHeader>
            <SheetTitle className="font-mono text-base">
              {version.model.id} · test results
            </SheetTitle>
            <SheetDescription>
              {version.summary.holdout_examples} requests the model never
              trained on, each answered fresh by{" "}
              <span className="font-mono">
                {version.summary.comparison_model_id}
              </span>{" "}
              and by this model, judged in both orders. Showing {results.length}{" "}
              of {version.summary.holdout_examples}.
            </SheetDescription>
          </SheetHeader>
          <div className="mt-5 divide-y rounded-lg border">
            {results.map((row) => (
              <div key={row.index} className="p-4">
                <div className="mb-2 flex items-center justify-between gap-3">
                  <p className="text-xs text-muted-foreground">#{row.index}</p>
                  <Badge
                    variant="outline"
                    className={verdictClass[row.verdict]}
                  >
                    {row.verdict}
                  </Badge>
                </div>
                <p className="mb-3 text-sm leading-6">{row.request_preview}</p>
                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-md border bg-muted/40 p-3">
                    <p className="mb-1 font-mono text-[10px] text-muted-foreground">
                      {version.summary.comparison_model_id}
                    </p>
                    <p className="font-mono text-[11px] leading-5 break-words whitespace-pre-wrap">
                      {row.comparison_response}
                    </p>
                  </div>
                  <div className="rounded-md border p-3">
                    <p className="mb-1 font-mono text-[10px] text-muted-foreground">
                      {version.model.id}
                    </p>
                    <p className="font-mono text-[11px] leading-5 break-words whitespace-pre-wrap">
                      {row.fine_tuned_response}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </>
      ) : null}
    </SheetContent>
  </Sheet>
);
