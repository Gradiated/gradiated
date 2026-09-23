import { describe, expect, it } from "vitest";

import type { TaskStats, VersionView } from "@/store/fine-tuning-types";
import {
  MAX_VERSION_ADOPTION,
  taskTraffic,
  type TrafficMetric,
} from "@/store/mock-traffic";
import { DAY_MS } from "@/store/mock-values";

import { defined, seededSupportTriage } from "./support/fine-tuning";

const {
  seed,
  task: supportTriage,
  version: seededVersion,
} = seededSupportTriage();
const stats = defined(seed.stats[supportTriage.id]);
const NOW = Date.parse("2026-09-23T12:00:00.000Z");

const versionCreated = (daysAgo: number): VersionView => ({
  ...seededVersion,
  model: {
    ...seededVersion.model,
    id: `support-triage-${daysAgo}d`,
    created_at: new Date(NOW - daysAgo * DAY_MS).toISOString(),
  },
});

const traffic = (
  versions: readonly VersionView[],
  {
    days = 30,
    metric = "requests",
    taskStats = stats,
  }: { days?: number; metric?: TrafficMetric; taskStats?: TaskStats } = {},
) =>
  taskTraffic({
    task: supportTriage,
    versions,
    traces: seed.traces,
    stats: taskStats,
    days,
    metric,
    now: NOW,
  });

const dailyTotals = (rows: ReturnType<typeof traffic>["rows"]) =>
  rows.map((row) =>
    Object.values(row).reduce<number>(
      (total, value) => (typeof value === "number" ? total + value : total),
      0,
    ),
  );

describe("taskTraffic", () => {
  it("returns one row per day ending today", () => {
    const { rows } = traffic([], { days: 7 });

    expect(rows.map((row) => row.date)).toEqual([
      "2026-09-17",
      "2026-09-18",
      "2026-09-19",
      "2026-09-20",
      "2026-09-21",
      "2026-09-22",
      "2026-09-23",
    ]);
  });

  it("moves requests to versions without changing each day's total", () => {
    const withoutVersions = traffic([]);
    const withVersions = traffic([versionCreated(20), versionCreated(5)]);

    expect(dailyTotals(withVersions.rows)).toEqual(
      dailyTotals(withoutVersions.rows),
    );
    expect(withVersions.series.map((entry) => entry.kind)).toContain("version");
  });

  it("gives a version no traffic before it was created", () => {
    const version = versionCreated(10);
    const created = version.model.created_at.slice(0, 10);
    const { rows } = traffic([version]);

    for (const row of rows) {
      if (String(row.date) >= created) continue;

      expect(row[version.model.id]).toBe(0);
    }
    expect(rows.at(-1)?.[version.model.id]).toBeGreaterThan(0);
  });

  it("caps a version's share of traffic", () => {
    const version = versionCreated(170);
    const { rows } = traffic([version]);
    const totals = dailyTotals(rows);

    for (const [index, row] of rows.entries()) {
      const total = totals[index] ?? 0;

      expect(row[version.model.id]).toBe(
        Math.round(total * MAX_VERSION_ADOPTION),
      );
    }
  });

  it("counts tokens as requests times the task's tokens per request", () => {
    const tokensPerRequest = stats.tokens_7d / stats.requests_7d;
    const versions = [versionCreated(5)];
    const requests = traffic(versions, { days: 1 });
    const tokens = defined(
      traffic(versions, { days: 1, metric: "tokens" }).rows[0],
    );

    for (const { key } of requests.series) {
      expect(tokens[key]).toBe(
        Math.round(Number(requests.rows[0]?.[key]) * tokensPerRequest),
      );
    }
  });

  it("shows no traffic for a task without recorded requests", () => {
    const empty = {
      requests_7d: 0,
      tokens_7d: 0,
      usable_traces_since_last_run: 0,
    };

    for (const metric of ["requests", "tokens", "cost"] as const) {
      expect(
        dailyTotals(
          traffic([versionCreated(5)], { metric, taskStats: empty }).rows,
        ),
      ).toEqual(Array.from({ length: 30 }, () => 0));
    }
  });
});
