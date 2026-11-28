import type { models } from "@gradiated/grad";

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

export type UsageKind = models.UsageKind;
export type UsageSummary = models.UsageSummary;

export const USAGE_KIND_LABEL: Record<UsageKind, string> = {
  training: "Training",
  eval: "Evals",
  scoring: "Scoring",
  labeling: "Labeling",
  teacher: "Teacher answers",
};
