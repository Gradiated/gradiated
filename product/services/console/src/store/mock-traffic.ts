import type {
  TaskRow,
  TaskStats,
  TraceGenerationRow,
  VersionView,
} from "@/store/fine-tuning-types";
import {
  DAY_MS,
  isoAt,
  priceForModel,
  seededRandom,
} from "@/store/mock-values";

const TRAFFIC_JITTER_DAYS = 180;
const TRAFFIC_PROVIDER_LIMIT = 3;
const PRIMARY_PROVIDER_SHARE = 0.8;
const VERSION_ADOPTION_PER_DAY = 0.065;
export const MAX_VERSION_ADOPTION = 0.9;
const INPUT_TOKEN_SHARE = 0.75;

export type TrafficMetric = "cost" | "requests" | "tokens";

export interface TaskTraffic {
  rows: Record<string, number | string>[];
  series: { key: string; kind: "provider" | "version" }[];
}

export const taskTraffic = ({
  task,
  versions,
  traces,
  stats,
  days,
  metric,
  now,
}: {
  task: TaskRow;
  versions: readonly VersionView[];
  traces: readonly TraceGenerationRow[];
  stats: TaskStats;
  days: number;
  metric: TrafficMetric;
  now: number;
}): TaskTraffic => {
  const seenModels = [
    ...new Set(
      traces.filter((row) => row.task === task.slug).map((row) => row.model),
    ),
  ].slice(0, TRAFFIC_PROVIDER_LIMIT);
  const providers = seenModels.length ? seenModels : [task.comparison_model_id];
  const ownVersions = versions.toSorted((a, b) =>
    a.model.created_at.localeCompare(b.model.created_at),
  );
  const baseModels = new Map(
    ownVersions.map((version) => [
      version.model.id,
      version.model.base_model_id,
    ]),
  );
  const dailyRequests = Math.round(stats.requests_7d / 7);
  const tokensPerRequest = stats.tokens_7d / Math.max(1, stats.requests_7d);

  const measure = (model: string, requests: number) => {
    if (metric === "requests") return requests;

    const tokens = requests * tokensPerRequest;
    if (metric === "tokens") return Math.round(tokens);

    const [input, output] = priceForModel(model, baseModels.get(model));
    const usd =
      (tokens * INPUT_TOKEN_SHARE * input +
        tokens * (1 - INPUT_TOKEN_SHARE) * output) /
      1_000_000;

    return Number(usd.toFixed(5));
  };

  const dayRow = (daysAgo: number): Record<string, number | string> => {
    const day = now - daysAgo * DAY_MS;
    const jitter =
      0.75 +
      seededRandom(`${task.id}-${daysAgo % TRAFFIC_JITTER_DAYS}`)() * 0.5;
    const total = Math.round(dailyRequests * jitter);
    const requests = new Map<string, number>();
    let remaining = total;

    for (const version of ownVersions.toReversed()) {
      const daysSince = (day - Date.parse(version.model.created_at)) / DAY_MS;
      const adoption =
        daysSince < 0
          ? 0
          : Math.min(
              MAX_VERSION_ADOPTION,
              daysSince * VERSION_ADOPTION_PER_DAY,
            );
      const count = Math.min(remaining, Math.round(total * adoption));

      requests.set(version.model.id, count);
      remaining -= count;
    }

    let assigned = 0;
    for (const [index, model] of providers.entries()) {
      const isLast = index === providers.length - 1;
      const share =
        index === 0
          ? PRIMARY_PROVIDER_SHARE
          : (1 - PRIMARY_PROVIDER_SHARE) / Math.max(1, providers.length - 1);
      const count = isLast
        ? Math.max(0, remaining - assigned)
        : Math.round(remaining * share);

      requests.set(model, count);
      assigned += count;
    }

    return {
      date: isoAt(day).slice(0, 10),
      ...Object.fromEntries(
        [...requests].map(([model, count]) => [model, measure(model, count)]),
      ),
    };
  };

  return {
    rows: Array.from({ length: days }, (_, index) => dayRow(days - 1 - index)),
    series: [
      ...providers.map((key) => ({ key, kind: "provider" as const })),
      ...ownVersions.map((version) => ({
        key: version.model.id,
        kind: "version" as const,
      })),
    ],
  };
};
