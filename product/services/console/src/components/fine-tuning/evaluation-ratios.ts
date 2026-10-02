import { formatNanoUsd, formatRatio, type Ratio } from "@/lib/format";
import type { EvaluationSummary } from "@/store/fine-tuning-types";

const REQUESTS_PER_COST_UNIT = 1_000;
export const costAdvantage = (summary: EvaluationSummary): Ratio => {
  if (!summary.cost_per_request_nano_usd)
    return formatRatio(NaN, "cheaper", "more expensive");
  const { comparison, fine_tuned } = summary.cost_per_request_nano_usd;

  return formatRatio(comparison / fine_tuned, "cheaper", "more expensive");
};

export const speedAdvantage = (summary: EvaluationSummary): Ratio => {
  const { comparison, fine_tuned } = summary.output_tokens_per_second;

  return formatRatio(fine_tuned / comparison, "faster", "slower");
};

export const costPer1kRequests = (summary: EvaluationSummary): string => {
  if (!summary.cost_per_request_nano_usd) return "Not measured";
  const { comparison, fine_tuned } = summary.cost_per_request_nano_usd;

  const estimate = summary.cost_basis ? " (estimated)" : "";

  return `${formatNanoUsd(fine_tuned * REQUESTS_PER_COST_UNIT)} vs ${formatNanoUsd(comparison * REQUESTS_PER_COST_UNIT)} per 1k requests${estimate}`;
};

export const outputSpeed = (summary: EvaluationSummary): string => {
  const { comparison, fine_tuned } = summary.output_tokens_per_second;

  return `${fine_tuned.toFixed(1)} vs ${comparison.toFixed(1)} output tokens/s`;
};
