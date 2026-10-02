import { modelDisplayName } from "@gradiated/contracts/model-catalog";
import { Info } from "lucide-react";

import {
  costAdvantage,
  costPer1kRequests,
  outputSpeed,
  speedAdvantage,
} from "@/components/fine-tuning/evaluation-ratios";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { formatPercent, type Ratio } from "@/lib/format";
import type {
  EvaluationSummary,
  JudgeOutcome,
} from "@/store/fine-tuning-types";

const SEGMENTS = [
  { key: "win", label: "Better", className: "bg-[#6e7f31] text-white" },
  { key: "tie", label: "Equivalent", className: "bg-[#dedbd0] text-[#5a5850]" },
  { key: "loss", label: "Worse", className: "bg-[#e4c880] text-[#5c4710]" },
] as const;

const RATIO_TONE_CLASS: Record<Ratio["tone"], string> = {
  good: "text-[#475617]",
  bad: "text-amber-800",
  neutral: "text-muted-foreground",
};

export const RatioLabel = ({
  ratio,
  detail,
}: {
  ratio: Ratio;
  detail?: string;
}) => {
  const label = (
    <span className={`font-medium ${RATIO_TONE_CLASS[ratio.tone]}`}>
      {ratio.label}
    </span>
  );
  if (!detail) return label;

  return (
    <Tooltip>
      <TooltipTrigger asChild>{label}</TooltipTrigger>
      <TooltipContent side="top" className="text-xs">
        {detail}
      </TooltipContent>
    </Tooltip>
  );
};

const Comparison = ({
  name,
  ratio,
  numbers,
}: {
  name: string;
  ratio: Ratio;
  numbers: string;
}) => (
  <span>
    {name} <RatioLabel ratio={ratio} />{" "}
    <span className="text-muted-foreground">· {numbers}</span>
  </span>
);

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
      ? `Resolved comparisons: ${SEGMENTS.map((segment) => `${segment.label} ${formatPercent(outcome[segment.key] / resolved)}`).join(", ")}. ${formatPercent(outcome.unresolved)} unresolved overall.`
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
              title={`${segment.label} ${formatPercent(share)} of resolved comparisons`}
            >
              {labels && share >= 0.12 ? (
                <span className="truncate px-1 text-xs font-medium tabular-nums">
                  {segment.label} {formatPercent(share)}
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

export const EvaluationPanel = ({
  summary,
  onViewResults,
}: {
  summary: EvaluationSummary;
  onViewResults?: () => void;
}) => {
  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-4 text-sm">
        <p>
          Compared with{" "}
          <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[0.85em]">
            {modelDisplayName(summary.comparison_model_id)}
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
                {modelDisplayName(summary.judge_model_id)}
              </code>
              <Info className="size-3.5" />
            </button>
          </TooltipTrigger>
          <TooltipContent side="left" className="max-w-sm text-xs leading-5">
            <p className="mb-2">
              {summary.holdout_examples} held-out examples based on production
              data were evaluated.
            </p>
            <p className="mb-2">
              For each request, the judge (
              {modelDisplayName(summary.judge_model_id)}) saw this model's
              answer and a fresh answer from the comparison model (
              {modelDisplayName(summary.comparison_model_id)}), unlabelled.
            </p>
            <p>
              {summary.judging_method === "randomized_single"
                ? "Each pair was judged once, with randomized answer order, and the judge decides which is better."
                : "Each pair was judged in both answer orders, and the judge decides which is better."}
            </p>
          </TooltipContent>
        </Tooltip>
      </div>

      <OutcomeBar outcome={summary.vs_comparison} />

      <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1 text-xs text-foreground tabular-nums">
        {summary.cost_per_request_nano_usd ? (
          <Comparison
            name="Cost"
            ratio={costAdvantage(summary)}
            numbers={costPer1kRequests(summary)}
          />
        ) : (
          <span>
            Cost{" "}
            <RatioLabel
              ratio={costAdvantage(summary)}
              detail={costPer1kRequests(summary)}
            />
          </span>
        )}
        <Comparison
          name="Speed"
          ratio={speedAdvantage(summary)}
          numbers={outputSpeed(summary)}
        />
        <span>
          Resolved{" "}
          <span className="font-medium">
            {formatPercent(1 - summary.vs_comparison.unresolved)}
          </span>
        </span>
        <span>
          Errors{" "}
          <span className="font-medium">
            {formatPercent(summary.error_rate)}
          </span>
        </span>

        <Button
          variant="link"
          size="sm"
          className="h-auto shrink-0 p-0 text-xs"
          onClick={onViewResults}
          disabled={!onViewResults}
        >
          View test results →
        </Button>
      </div>
    </div>
  );
};
