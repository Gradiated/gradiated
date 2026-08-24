import * as React from "react";
import * as RechartsPrimitive from "recharts";

import { cn } from "@/lib/utils";

export type ChartConfig = Record<
  string,
  {
    label?: React.ReactNode;
    color?: string;
  }
>;

const ChartContext = React.createContext<{ config: ChartConfig } | null>(null);

const useChart = () => {
  const context = React.useContext(ChartContext);
  if (!context) throw new Error("useChart must be used within ChartContainer");
  return context;
};

export const ChartContainer = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<"div"> & {
    config: ChartConfig;
    children: React.ComponentProps<
      typeof RechartsPrimitive.ResponsiveContainer
    >["children"];
  }
>(({ id, className, children, config, style, ...props }, ref) => {
  const chartId = React.useId().replace(/:/g, "");
  const cssVariables = Object.fromEntries(
    Object.entries(config)
      .filter(([, item]) => item.color)
      .map(([key, item]) => [`--color-${key}`, item.color]),
  ) as React.CSSProperties;

  return (
    <ChartContext.Provider value={{ config }}>
      <div
        ref={ref}
        data-chart={id ?? chartId}
        className={cn(
          "flex aspect-video justify-center text-xs [&_.recharts-cartesian-axis-tick_text]:fill-muted-foreground [&_.recharts-cartesian-grid_line]:stroke-border/60 [&_.recharts-curve.recharts-tooltip-cursor]:stroke-border [&_.recharts-layer]:outline-none [&_.recharts-sector]:outline-none [&_.recharts-surface]:outline-none",
          className,
        )}
        style={{ ...cssVariables, ...style }}
        {...props}
      >
        <RechartsPrimitive.ResponsiveContainer>
          {children}
        </RechartsPrimitive.ResponsiveContainer>
      </div>
    </ChartContext.Provider>
  );
});
ChartContainer.displayName = "ChartContainer";

export const ChartTooltip = RechartsPrimitive.Tooltip;

type TooltipPayload = {
  color?: string;
  dataKey?: string | number;
  name?: string | number;
  value?: string | number;
  payload?: Record<string, unknown>;
};

export const ChartTooltipContent = React.forwardRef<
  HTMLDivElement,
  React.ComponentProps<"div"> & {
    active?: boolean;
    hideLabel?: boolean;
    label?: string | number;
    labelFormatter?: (label: string | number) => React.ReactNode;
    payload?: readonly TooltipPayload[];
    valueFormatter?: (
      value: string | number,
      dataKey: string,
    ) => React.ReactNode;
  }
>(
  (
    {
      active,
      className,
      hideLabel,
      label,
      labelFormatter,
      payload,
      valueFormatter,
    },
    ref,
  ) => {
    const { config } = useChart();
    if (!active || !payload?.length) return null;

    return (
      <div
        ref={ref}
        className={cn(
          "grid min-w-32 gap-1.5 rounded-lg border bg-background px-3 py-2 text-xs shadow-xl",
          className,
        )}
      >
        {!hideLabel && label !== undefined ? (
          <div className="font-medium">
            {labelFormatter ? labelFormatter(label) : label}
          </div>
        ) : null}
        <div className="grid gap-1.5">
          {payload.map((item) => {
            const key = String(item.dataKey ?? item.name ?? "value");
            return (
              <div
                key={key}
                className="flex min-w-32 items-center justify-between gap-4"
              >
                <span className="flex items-center gap-2 text-muted-foreground">
                  <span
                    className="size-2 rounded-[2px]"
                    style={{ backgroundColor: item.color }}
                  />
                  {config[key]?.label ?? item.name ?? key}
                </span>
                <span className="font-mono font-medium tabular-nums text-foreground">
                  {valueFormatter
                    ? valueFormatter(item.value ?? 0, key)
                    : item.value?.toLocaleString()}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    );
  },
);
ChartTooltipContent.displayName = "ChartTooltipContent";
