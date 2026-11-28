import type { EvalReport, RecipeKind } from "@/lib/grad/types";

export interface ReportRow {
  label: string;
  value: string;
}

type Format = "number" | "percent" | "count" | "text" | "list" | "boolean";

const FIELDS: Partial<
  Record<RecipeKind, [keyof EvalReport, string, Format][]>
> = {
  sft: [
    ["evalLoss", "Eval loss", "number"],
    ["evalTokenAccuracy", "Token accuracy", "percent"],
    ["trainedTokenFraction", "Trained tokens", "percent"],
    ["trainExamples", "Train examples", "count"],
    ["evalExamples", "Eval examples", "count"],
    ["truncated", "Truncated", "count"],
  ],
  dpo: [
    ["preferenceAccuracy", "Preference accuracy", "percent"],
    ["rewardMargin", "Reward margin", "number"],
    ["evalLoss", "Eval loss", "number"],
    ["beta", "Beta", "number"],
    ["trainPairs", "Train pairs", "count"],
    ["evalPairs", "Eval pairs", "count"],
    ["droppedRecords", "Dropped records", "count"],
  ],
  reward: [
    ["preferenceAccuracy", "Preference accuracy", "percent"],
    ["rewardMargin", "Reward margin", "number"],
    ["pointwiseBrier", "Pointwise Brier", "number"],
    ["trainPairs", "Train pairs", "count"],
    ["evalPairs", "Eval pairs", "count"],
    ["trainPoints", "Train points", "count"],
    ["evalPoints", "Eval points", "count"],
  ],
  router: [
    ["evalLoss", "Eval loss", "number"],
    ["candidates", "Candidates", "list"],
    ["fallbackModel", "Fallback model", "text"],
    ["fallbackQuality", "Fallback quality", "percent"],
    ["routesAnyTraffic", "Routes any traffic", "boolean"],
    ["selectionExamples", "Selection examples", "count"],
  ],
  decision: [
    ["evalLoss", "Eval loss", "number"],
    ["ece", "Calibration error (ECE)", "number"],
    ["evalExamples", "Eval examples", "count"],
    ["selectionExamples", "Selection examples", "count"],
  ],
  cartridge: [
    ["evalKl", "Eval KL", "number"],
    ["noContextKl", "KL without context", "number"],
    ["klReduction", "KL reduction", "percent"],
    ["numTokens", "Cartridge tokens", "count"],
    ["teacher", "Teacher", "text"],
  ],
  distill: [
    ["evalKl", "Eval KL", "number"],
    ["baseKl", "Base KL", "number"],
    ["klReduction", "KL reduction", "percent"],
    ["evalLoss", "Eval loss", "number"],
    ["evalTokenAccuracy", "Token accuracy", "percent"],
    ["teacher", "Teacher", "text"],
    ["rollout", "Rollout", "text"],
  ],
  embedding: [
    ["recallAt1", "Recall@1", "percent"],
    ["recallAt5", "Recall@5", "percent"],
    ["recallAt10", "Recall@10", "percent"],
    ["mrr", "MRR", "number"],
    ["corpusSize", "Corpus size", "count"],
    ["trainPairs", "Train pairs", "count"],
    ["evalPairs", "Eval pairs", "count"],
  ],
};

export const formatMetric = (value: number) =>
  Math.abs(value) >= 100
    ? value.toLocaleString("en-US", { maximumFractionDigits: 1 })
    : value.toPrecision(4).replace(/\.?0+$/, "");

export const formatShare = (value: number) =>
  `${(value * 100).toLocaleString("en-US", { maximumFractionDigits: 1 })}%`;

const formatValue = (value: unknown, format: Format): string | null => {
  if (value === null || value === undefined) return null;
  if (format === "list" && Array.isArray(value))
    return value.length ? value.join(", ") : null;
  if (format === "boolean" && typeof value === "boolean")
    return value ? "Yes" : "No";
  if (format === "text" && typeof value === "string") return value || null;
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  if (format === "percent") return formatShare(value);
  if (format === "count") return value.toLocaleString("en-US");

  return formatMetric(value);
};

const camel = (name: string) =>
  name.replace(/_([a-z0-9])/g, (_, letter: string) => letter.toUpperCase());

export const METRIC_LABEL: Record<string, string> = {
  eval_loss: "Eval loss",
  preference_accuracy: "Preference accuracy",
  eval_kl: "Eval KL",
  recall_at_10: "Recall@10",
};

export const metricLabel = (name: string) =>
  METRIC_LABEL[name] ?? name.replaceAll("_", " ");

const SHARE_METRICS = /accuracy|recall/;

export const selectionMetric = (report: EvalReport) => {
  const value = report[camel(report.metricName)];

  return {
    name: metricLabel(report.metricName),
    share: SHARE_METRICS.test(report.metricName),
    mode:
      report.metricMode ??
      (/loss|kl/.test(report.metricName) ? ("min" as const) : ("max" as const)),
    value: typeof value === "number" ? value : null,
  };
};

export const evalReportRows = (
  kind: RecipeKind,
  report: EvalReport,
): ReportRow[] => {
  const rows: ReportRow[] = [];

  for (const [field, label, format] of FIELDS[kind] ?? []) {
    const value = formatValue(report[field], format);
    if (value !== null) rows.push({ label, value });
  }

  const pareto = report.paretoSummary;

  if (kind === "router" && pareto) {
    const drop = formatValue(pareto.qualityDrop, "percent");
    const ci = pareto.qualityDropCi95;

    for (const [label, value] of [
      ["Offload rate", formatValue(pareto.offloadRate, "percent")],
      ["Cost savings", formatValue(pareto.costSavingsPct, "percent")],
      [
        "Quality drop",
        drop && ci?.length === 2
          ? `${drop} (95% CI ${formatShare(ci[0] ?? 0)} to ${formatShare(ci[1] ?? 0)})`
          : drop,
      ],
    ] as const) {
      if (value !== null) rows.push({ label, value });
    }
  }

  if (kind === "embedding" && report.baseline?.recallAt10 != null) {
    rows.push({
      label: "Base model Recall@10",
      value: formatShare(report.baseline.recallAt10),
    });
  }

  return rows;
};
