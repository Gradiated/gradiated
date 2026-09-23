import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";

import { Card, CardContent, CardHeader } from "@/components/ui/card";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { formatUsd } from "@/lib/format";
import { compactNumber, utcDayLabel } from "@/pages/chart-format";
import { SegmentedControl } from "@/pages/segmented-control";
import type { TaskRow } from "@/store/fine-tuning-types";
import {
  useMockFineTuning,
  useTaskStats,
  useTaskVersions,
} from "@/store/mock-fine-tuning";
import {
  taskTraffic,
  type TaskTraffic,
  type TrafficMetric,
} from "@/store/mock-traffic";

const SERIES_COLORS = {
  provider: { palette: ["#171714", "#9c988a", "#cfcbbd"], fallback: "#cfcbbd" },
  version: { palette: ["#6e7f31", "#b6cf5a", "#3f4a1a"], fallback: "#6e7f31" },
} as const;

const METRIC_OPTIONS = [
  { value: "cost", label: "Cost" },
  { value: "requests", label: "Requests" },
  { value: "tokens", label: "Tokens" },
] as const satisfies readonly { value: TrafficMetric; label: string }[];

const RANGE_OPTIONS = [
  { value: 30, label: "30d" },
  { value: 90, label: "90d" },
  { value: 180, label: "180d" },
] as const;

type RangeDays = (typeof RANGE_OPTIONS)[number]["value"];

const withColors = (series: TaskTraffic["series"]) =>
  series.map((entry, index) => {
    const { palette, fallback } = SERIES_COLORS[entry.kind];
    const position = series
      .slice(0, index)
      .filter((candidate) => candidate.kind === entry.kind).length;

    return { ...entry, color: palette[position] ?? fallback };
  });

export const TrafficChart = ({ task }: { task: TaskRow }) => {
  const [days, setDays] = useState<RangeDays>(30);
  const [metric, setMetric] = useState<TrafficMetric>("cost");
  const versions = useTaskVersions(task.id);
  const traces = useMockFineTuning((state) => state.traces);
  const stats = useTaskStats(task.id);

  const { rows, series } = useMemo(() => {
    const traffic = taskTraffic({
      task,
      versions,
      traces,
      stats,
      days,
      metric,
      now: Date.now(),
    });

    return { rows: traffic.rows, series: withColors(traffic.series) };
  }, [task, versions, traces, stats, days, metric]);

  const chartConfig = Object.fromEntries(
    series.map((entry) => [
      entry.key,
      { label: entry.key, color: entry.color },
    ]),
  ) satisfies ChartConfig;

  const format = (value: number) => {
    if (metric !== "cost") return compactNumber(value);

    return value > 0 && value < 0.1 ? `$${value.toFixed(3)}` : formatUsd(value);
  };

  return (
    <section>
      <h2 className="mb-2 text-sm font-medium">Traffic</h2>
      <Card className="shadow-sm">
        <CardHeader className="flex-row items-center justify-between gap-4 border-b p-4">
          <SegmentedControl
            value={metric}
            onChange={setMetric}
            options={METRIC_OPTIONS}
          />
          <SegmentedControl
            value={days}
            onChange={setDays}
            options={RANGE_OPTIONS}
          />
        </CardHeader>
        <CardContent className="p-5">
          <ChartContainer config={chartConfig} className="h-[240px] w-full">
            <BarChart
              data={rows}
              margin={{ left: 4, right: 8, top: 12 }}
              barCategoryGap={days === 30 ? 3 : 1}
            >
              <CartesianGrid vertical={false} />
              <XAxis
                dataKey="date"
                axisLine={false}
                tickLine={false}
                minTickGap={32}
                tickFormatter={utcDayLabel}
              />
              <YAxis
                axisLine={false}
                tickLine={false}
                width={52}
                tickFormatter={(value: number) => format(value)}
              />
              <ChartTooltip
                content={
                  <ChartTooltipContent
                    labelFormatter={(label) => utcDayLabel(String(label))}
                    valueFormatter={(value) => format(Number(value))}
                  />
                }
              />
              {series.map((entry, index) => (
                <Bar
                  key={entry.key}
                  dataKey={entry.key}
                  stackId="traffic"
                  fill={entry.color}
                  radius={index === series.length - 1 ? [3, 3, 0, 0] : 0}
                />
              ))}
            </BarChart>
          </ChartContainer>
        </CardContent>
      </Card>
    </section>
  );
};
