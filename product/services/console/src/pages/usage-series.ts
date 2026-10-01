import type { UsageRange, UsageSummary } from "@/api/queries";
import { NANO_USD_PER_USD } from "@/lib/money";
import type { Option } from "@/components/option-select";

export const RANGE_OPTIONS = [
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
  { value: "90d", label: "Last 90 days" },
] as const satisfies readonly Option<string>[];

export type RangeKey = (typeof RANGE_OPTIONS)[number]["value"];

const RANGE_DAYS: Record<RangeKey, number> = { "7d": 7, "30d": 30, "90d": 90 };

type DailyUsage = UsageSummary["daily"][number];

export interface UsagePoint {
  date: string;
  cost: number;
  requests: number;
  tokens: number;
}

export const usageDateRange = (key: RangeKey, now: Date): UsageRange => {
  const to = new Date(now);
  to.setUTCHours(24, 0, 0, 0);

  const from = new Date(to);
  from.setUTCDate(from.getUTCDate() - RANGE_DAYS[key]);

  return { from: from.toISOString(), to: to.toISOString() };
};

export const dailyUsageSeries = (
  daily: readonly DailyUsage[],
  range: UsageRange,
): UsagePoint[] => {
  const points = new Map(daily.map((point) => [point.date, point]));
  const end = new Date(range.to);
  const series: UsagePoint[] = [];

  for (
    const day = new Date(range.from);
    day < end;
    day.setUTCDate(day.getUTCDate() + 1)
  ) {
    const date = day.toISOString().slice(0, 10);
    const point = points.get(date);

    series.push({
      date,
      cost: Number(point?.charge ?? 0) / Number(NANO_USD_PER_USD),
      requests: Number(point?.generation_count ?? 0),
      tokens:
        Number(point?.input_tokens ?? 0) + Number(point?.output_tokens ?? 0),
    });
  }

  return series;
};
