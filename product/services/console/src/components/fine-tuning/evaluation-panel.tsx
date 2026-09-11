import { Info } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  NANO,
  type EvaluationSummary,
  type JudgeOutcome,
} from "@/store/mock-fine-tuning";

const pct = (value: number) => `${Math.round(value * 100)}%`;
/** nano-USD → dollars, three decimals below $1. */
export const usdFromNano = (nano: number) => {
  const v = nano / NANO;
  return v < 1 ? `$${v.toFixed(3)}` : `$${v.toFixed(2)}`;
};

const SEGMENTS = [
  { key: "win", label: "Better", className: "bg-[#6e7f31] text-white" },
  { key: "tie", label: "Equivalent", className: "bg-[#dedbd0] text-[#5a5850]" },
  { key: "loss", label: "Worse", className: "bg-[#e4c880] text-[#5c4710]" },
] as const;

/** `value` > 1 is good: "14× cheaper", "1.6× faster". */
export const ratioLabel = (value: number, good: string, bad: string) => {
  const isGood = value >= 1;
  const factor = isGood ? value : 1 / value;
  return {
    isGood,
    label: `${factor >= 10 ? Math.round(factor) : factor.toFixed(1)}× ${isGood ? good : bad}`,
  };
};

const Comparison = ({
  name,
  ratio,
  numbers,
}: {
  name: string;
  ratio: { isGood: boolean; label: string };
  numbers: string;
}) => (
  <span>
    {name}{" "}
    <span
      className={`font-medium ${ratio.isGood ? "text-[#475617]" : "text-amber-800"}`}
    >
      {ratio.label}
    </span>{" "}
    <span className="text-muted-foreground">· {numbers}</span>
  </span>
);

/** Resolved outcomes fill the bar. Report unresolved results separately. */
export const OutcomeBar = ({
  outcome,
  height = "h-9",
  labels = true,
}: {
  outcome: JudgeOutcome;
  height?: string;
  labels?: boolean;
}) => {
  const resolved = outcome.win + outcome.tie + outcome.loss;
  const description =
    resolved > 0
      ? `Resolved comparisons: ${SEGMENTS.map((segment) => `${segment.label} ${pct(outcome[segment.key] / resolved)}`).join(", ")}. ${pct(outcome.unresolved)} unresolved overall.`
      : "No resolved comparisons.";

  return (
    <div
      role="img"
      aria-label={description}
      className={`flex ${height} w-full overflow-hidden rounded-md`}
    >
      {resolved > 0 ? (
        SEGMENTS.map((segment) => {
          const value = outcome[segment.key];
          const share = value / resolved;
          return (
            <div
              key={segment.key}
              className={`flex min-w-0 items-center justify-center overflow-hidden ${segment.className}`}
              style={{ flex: `${share * 100} 1 0%` }}
              title={`${segment.label} ${pct(share)} of resolved comparisons`}
            >
              {labels && share >= 0.12 ? (
                <span className="truncate px-1 text-xs font-medium tabular-nums">
                  {segment.label} {pct(share)}
                </span>
              ) : null}
            </div>
          );
        })
      ) : (
        <div className="flex w-full items-center justify-center bg-muted text-xs text-muted-foreground">
          {labels ? "No resolved comparisons" : null}
        </div>
      )}
    </div>
  );
};

/** Exactly what the console shows of an `EvaluationSummary`: results, never a verdict. */
export const EvaluationPanel = ({
  summary,
  onViewResults,
}: {
  summary: EvaluationSummary;
  onViewResults?: () => void;
}) => {
  const cost = summary.cost_per_request_nano_usd;
  const tps = summary.output_tokens_per_second;

  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-4 text-sm">
        <p>
          Compared with{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[0.85em]">
            {summary.comparison_model_id}
          </code>
        </p>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              aria-label="How this is measured"
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            >
              judged by{" "}
              <code className="rounded bg-muted px-1 py-0.5 font-mono text-[0.9em]">
                {summary.judge_model_id}
              </code>
              <Info className="size-3.5" />
            </button>
          </TooltipTrigger>
          <TooltipContent side="left" className="max-w-sm text-xs leading-5">
            <p className="mb-2">
              {summary.holdout_examples} requests from {summary.holdout_groups}{" "}
              sessions were kept out of training. Each session counts once.
            </p>
            <p className="mb-2">
              For each request, {summary.judge_model_id} saw this model's answer
              and a fresh {summary.comparison_model_id} answer, unlabelled, in
              both orders, and picked the better one. Unresolved means the two
              orders disagreed.
            </p>
            <p>Nothing here blocks promotion. You decide.</p>
          </TooltipContent>
        </Tooltip>
      </div>

      <OutcomeBar outcome={summary.vs_comparison} />
      <p className="mt-1.5 text-xs text-muted-foreground">
        Resolved comparisons · {pct(summary.vs_comparison.unresolved)}{" "}
        unresolved overall
      </p>

      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-foreground tabular-nums">
        <Comparison
          name="Cost"
          ratio={ratioLabel(
            cost.comparison / Math.max(1, cost.fine_tuned),
            "cheaper",
            "more expensive",
          )}
          numbers={`${usdFromNano(cost.fine_tuned * 1000)} vs ${usdFromNano(cost.comparison * 1000)} per 1k requests`}
        />
        <Comparison
          name="Speed"
          ratio={ratioLabel(
            tps.fine_tuned / Math.max(1, tps.comparison),
            "faster",
            "slower",
          )}
          numbers={`${tps.fine_tuned} vs ${tps.comparison} tok/s`}
        />
        <span>
          Errors <span className="font-medium">{pct(summary.error_rate)}</span>
        </span>
        {onViewResults ? (
          <Button
            variant="link"
            size="sm"
            className="ml-auto h-auto p-0 text-xs"
            onClick={onViewResults}
          >
            View test results →
          </Button>
        ) : null}
      </div>
    </div>
  );
};
