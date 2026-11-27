import { z } from "zod";

import type { Option } from "@/components/option-select";

export const USAGE_RANGE_OPTIONS = [
  { value: "month", label: "This month" },
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
  { value: "90d", label: "Last 90 days" },
] as const satisfies readonly Option<string>[];

export type UsageRangeKey = (typeof USAGE_RANGE_OPTIONS)[number]["value"];

export const USAGE_GROUP_OPTIONS = [
  { value: "day", label: "By day" },
  { value: "week", label: "By week" },
  { value: "model", label: "By model" },
  { value: "recipe", label: "By recipe" },
  { value: "kind", label: "By kind" },
] as const satisfies readonly Option<string>[];

export type UsageGroupBy = (typeof USAGE_GROUP_OPTIONS)[number]["value"];

export const isTimeGroup = (groupBy: UsageGroupBy) =>
  groupBy === "day" || groupBy === "week";

const isoDay = (date: Date) => date.toISOString().slice(0, 10);

// `to` is a UTC date, which the API reads as covering that whole day.
export const usageRange = (key: UsageRangeKey, now: Date) => {
  const to = isoDay(now);

  if (key === "month") {
    return {
      from: `${to.slice(0, 7)}-01`,
      to,
    };
  }

  const from = new Date(now);
  from.setUTCDate(from.getUTCDate() - (Number.parseInt(key, 10) - 1));

  return { from: isoDay(from), to };
};

const usageKind = z.enum([
  "training",
  "eval",
  "scoring",
  "labeling",
  "teacher",
]);

export type UsageKind = z.infer<typeof usageKind>;

export const USAGE_KIND_LABEL: Record<UsageKind, string> = {
  training: "Training",
  eval: "Evals",
  scoring: "Scoring",
  labeling: "Labeling",
  teacher: "Teacher answers",
};

const totals = { cost_usd: z.number(), tokens: z.number().int() };

const refTotal = z
  .object({
    id: z.string(),
    name: z.string().nullable(),
    kind: usageKind,
    ...totals,
  })
  .transform(({ cost_usd, ...rest }) => ({ ...rest, costUsd: cost_usd }));

// Mirrors `grad.usage.summary()` from SDKs after 0.2.0-alpha.3.
export const usageSummarySchema = z
  .object({
    from: z.string(),
    to: z.string(),
    ...totals,
    records: z.number().int(),
    by_kind: z.array(
      z
        .object({ kind: usageKind, ...totals, records: z.number().int() })
        .transform(({ cost_usd, ...rest }) => ({ ...rest, costUsd: cost_usd })),
    ),
    top_runs: z.array(refTotal),
    top_evals: z.array(refTotal),
    group_by: z.string().nullable(),
    groups: z.array(
      z
        .object({
          key: z.string().nullable(),
          ...totals,
          records: z.number().int(),
        })
        .transform(({ cost_usd, ...rest }) => ({ ...rest, costUsd: cost_usd })),
    ),
  })
  .transform((summary) => ({
    from: summary.from,
    to: summary.to,
    costUsd: summary.cost_usd,
    tokens: summary.tokens,
    records: summary.records,
    byKind: summary.by_kind,
    topRuns: summary.top_runs,
    topEvals: summary.top_evals,
    groupBy: summary.group_by,
    groups: summary.groups,
  }));

export type UsageSummary = z.infer<typeof usageSummarySchema>;
