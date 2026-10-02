import { QWEN_PLACEHOLDER_PRICING } from "@gradiated/contracts/model-catalog";
import { formatNanoUsd, formatRatio, type Ratio } from "@/lib/format";
import type { EvaluationSummary } from "@/store/fine-tuning-types";

const REQUESTS_PER_COST_UNIT = 1_000;
const inputRate = `$${(QWEN_PLACEHOLDER_PRICING.input_nano_usd_per_token / 1_000).toFixed(2)}`;
const outputRate = `$${(QWEN_PLACEHOLDER_PRICING.output_nano_usd_per_token / 1_000).toFixed(2)}`;

export const usesQwenPlaceholderPrice = (summary: EvaluationSummary) =>
  !summary.cost_per_request_nano_usd &&
  summary.comparison_model_id === QWEN_PLACEHOLDER_PRICING.model_id &&
  summary.vs_comparison.comparator_model_id ===
    QWEN_PLACEHOLDER_PRICING.model_id;

export const hasEvaluationCost = (summary: EvaluationSummary) =>
  Boolean(summary.cost_per_request_nano_usd) ||
  usesQwenPlaceholderPrice(summary);

export const costAdvantage = (summary: EvaluationSummary): Ratio => {
  if (usesQwenPlaceholderPrice(summary))
    return { tone: "neutral", label: `${inputRate} / ${outputRate}` };

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
  if (usesQwenPlaceholderPrice(summary))
    return `Temporary Qwen rates: ${inputRate} input and ${outputRate} output per 1M tokens. Historical request costs were not recorded.`;

  if (!summary.cost_per_request_nano_usd) return "Not measured";
  const { comparison, fine_tuned } = summary.cost_per_request_nano_usd;

  const basis =
    summary.cost_basis === "placeholder_output_only"
      ? " (output only, placeholder estimate; input and GPU costs excluded)"
      : "";

  return `${formatNanoUsd(fine_tuned * REQUESTS_PER_COST_UNIT)} vs ${formatNanoUsd(comparison * REQUESTS_PER_COST_UNIT)} per 1k requests${basis}`;
};

export const outputSpeed = (summary: EvaluationSummary): string => {
  const { comparison, fine_tuned } = summary.output_tokens_per_second;

  return `${fine_tuned.toFixed(1)} vs ${comparison.toFixed(1)} output tokens/s`;
};
