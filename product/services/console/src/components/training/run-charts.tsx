import { useMemo } from "react";
import { CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts";

import { SectionCard } from "@/components/training/training-ui";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { formatMetric, metricLabel } from "@/lib/grad/eval-report";
import { evalMetricNames, evalSeries, lossSeries } from "@/lib/grad/run-events";
import type { RunEvent } from "@/lib/grad/types";

const SERIES_COLORS = [
  "#171714",
  "#6e7f31",
  "#b0702c",
  "#4a6fa5",
  "#8c5a9e",
] as const;

const lossConfig = {
  loss: { label: "Train loss", color: SERIES_COLORS[0] },
  evalLoss: { label: "Eval loss", color: SERIES_COLORS[1] },
} satisfies ChartConfig;

const stepTick = (value: number) => value.toLocaleString("en-US");

const EmptyChart = ({ children }: { children: string }) => (
  <div className="grid h-[240px] place-items-center text-center text-sm text-muted-foreground">
    {children}
  </div>
);

export const LossChart = ({ events }: { events: readonly RunEvent[] }) => {
  const data = useMemo(() => lossSeries(events), [events]);
  const latest = data.at(-1);

  return (
    <SectionCard
      title="Loss"
      description={
        latest
          ? `Train ${formatMetric(latest.loss)} at step ${stepTick(latest.step)}`
          : "Updates live while the run trains."
      }
    >
      {data.length ? (
        <ChartContainer config={lossConfig} className="h-[240px] w-full">
          <LineChart data={data} margin={{ left: 4, right: 8, top: 8 }}>
            <CartesianGrid vertical={false} />
            <XAxis
              dataKey="step"
              type="number"
              domain={["dataMin", "dataMax"]}
              axisLine={false}
              tickLine={false}
              minTickGap={32}
              tickFormatter={stepTick}
            />
            <YAxis
              axisLine={false}
              tickLine={false}
              width={48}
              domain={["auto", "auto"]}
              tickFormatter={(value: number) => formatMetric(value)}
            />
            <ChartTooltip
              content={
                <ChartTooltipContent
                  labelFormatter={(label) => `Step ${stepTick(Number(label))}`}
                  valueFormatter={(value) => formatMetric(Number(value))}
                />
              }
            />
            <Line
              dataKey="loss"
              type="monotone"
              stroke="var(--color-loss)"
              strokeWidth={1.5}
              dot={false}
              isAnimationActive={false}
            />
            <Line
              dataKey="evalLoss"
              type="monotone"
              stroke="var(--color-evalLoss)"
              strokeWidth={2}
              dot={{ r: 3 }}
              connectNulls
              isAnimationActive={false}
            />
          </LineChart>
        </ChartContainer>
      ) : (
        <EmptyChart>No training steps yet.</EmptyChart>
      )}
    </SectionCard>
  );
};

export const EvalChart = ({ events }: { events: readonly RunEvent[] }) => {
  const points = useMemo(() => evalSeries(events), [events]);
  const names = useMemo(() => evalMetricNames(points), [points]);
  const config = Object.fromEntries(
    names.map((name, index) => [
      name,
      {
        label: metricLabel(name),
        color: SERIES_COLORS[index % SERIES_COLORS.length] ?? SERIES_COLORS[0],
      },
    ]),
  ) satisfies ChartConfig;
  const data = points.map((point) => ({ step: point.step, ...point.values }));

  return (
    <SectionCard
      title="Held-out evals"
      description={
        names.length
          ? names.map(metricLabel).join(" · ")
          : "Each eval step is also a checkpoint."
      }
    >
      {data.length ? (
        <ChartContainer config={config} className="h-[240px] w-full">
          <LineChart data={data} margin={{ left: 4, right: 8, top: 8 }}>
            <CartesianGrid vertical={false} />
            <XAxis
              dataKey="step"
              type="number"
              domain={["dataMin", "dataMax"]}
              axisLine={false}
              tickLine={false}
              minTickGap={32}
              tickFormatter={stepTick}
            />
            <YAxis
              axisLine={false}
              tickLine={false}
              width={48}
              domain={["auto", "auto"]}
              tickFormatter={(value: number) => formatMetric(value)}
            />
            <ChartTooltip
              content={
                <ChartTooltipContent
                  labelFormatter={(label) => `Step ${stepTick(Number(label))}`}
                  valueFormatter={(value) => formatMetric(Number(value))}
                />
              }
            />
            {names.map((name) => (
              <Line
                key={name}
                dataKey={name}
                type="monotone"
                stroke={`var(--color-${name})`}
                strokeWidth={2}
                dot={{ r: 3 }}
                connectNulls
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ChartContainer>
      ) : (
        <EmptyChart>No eval steps yet.</EmptyChart>
      )}
    </SectionCard>
  );
};
