import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import {
  ArrowRight,
  ChartNoAxesCombined,
  CircleDollarSign,
  LoaderCircle,
  RefreshCw,
  Sigma,
  Zap,
} from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  XAxis,
  YAxis,
} from "recharts";

import { getUsageSummary } from "@/api/queries";
import { AppShell } from "@/components/app-shell";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useProductContext } from "@/hooks/use-product-context";
import { formatNanoUsd, formatUsd } from "@/lib/format";

type RangeKey = "7d" | "30d" | "90d";
type ChartMetric = "cost" | "requests" | "tokens";

const rangeDays: Record<RangeKey, number> = { "7d": 7, "30d": 30, "90d": 90 };

const chartConfig = {
  cost: { label: "Cost", color: "#171714" },
  requests: { label: "Requests", color: "#6e7f31" },
  tokens: { label: "Tokens", color: "#6e7f31" },
} satisfies ChartConfig;

const modelChartConfig = {
  cost: { label: "Cost", color: "#171714" },
} satisfies ChartConfig;

const dateRange = (key: RangeKey) => {
  const to = new Date();
  to.setUTCHours(24, 0, 0, 0);
  const from = new Date(to);
  from.setUTCDate(from.getUTCDate() - rangeDays[key]);
  return { from: from.toISOString(), to: to.toISOString() };
};

const compactNumber = (value: string | number) =>
  new Intl.NumberFormat(undefined, {
    notation: "compact",
    maximumFractionDigits: 2,
  }).format(Number(value));

const formatDate = (value: string) =>
  new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));

export const UsagePage = () => {
  const context = useProductContext();
  const [rangeKey, setRangeKey] = useState<RangeKey>("30d");
  const [metric, setMetric] = useState<ChartMetric>("cost");
  const range = useMemo(() => dateRange(rangeKey), [rangeKey]);
  const usage = useQuery({
    queryKey: ["usage", context.organizationId, context.workspaceId, rangeKey],
    queryFn: () =>
      getUsageSummary(context.organizationId, context.workspaceId, range),
    enabled: Boolean(context.organizationId && context.workspaceId),
  });

  const chartData = useMemo(() => {
    const points = new Map(
      usage.data?.daily.map((point) => [point.date, point]),
    );
    const cursor = new Date(range.from);
    const end = new Date(range.to);
    const data: Array<{
      date: string;
      cost: number;
      requests: number;
      tokens: number;
    }> = [];
    while (cursor < end) {
      const date = cursor.toISOString().slice(0, 10);
      const point = points.get(date);
      data.push({
        date,
        cost: Number(point?.charge ?? 0) / 1_000_000_000,
        requests: Number(point?.generation_count ?? 0),
        tokens:
          Number(point?.input_tokens ?? 0) + Number(point?.output_tokens ?? 0),
      });
      cursor.setUTCDate(cursor.getUTCDate() + 1);
    }
    return data;
  }, [range, usage.data?.daily]);

  const totalTokens =
    BigInt(usage.data?.input_tokens ?? "0") +
    BigInt(usage.data?.output_tokens ?? "0");
  const successRate = Number(usage.data?.generation_count ?? 0)
    ? (Number(usage.data?.succeeded_count ?? 0) /
        Number(usage.data?.generation_count ?? 1)) *
      100
    : 0;

  return (
    <AppShell
      user={context.user}
      organizationId={context.organizationId}
      workspaces={context.workspaces}
      workspaceId={context.workspaceId}
      onSelectOrganization={context.selectOrganization}
      onSelectWorkspace={context.selectWorkspace}
      onSignOut={context.signOut}
      activePage="usage"
      pageTitle="Usage"
    >
      <main className="min-w-0 flex-1 px-5 py-8 lg:px-10 lg:py-10">
        <div className="mx-auto w-full max-w-7xl">
          <div className="mb-7 flex flex-col justify-between gap-5 sm:flex-row sm:items-end">
            <div>
              <h1 className="text-3xl font-semibold tracking-[-0.035em]">
                Usage
              </h1>
              <p className="mt-2 text-sm leading-6 text-muted-foreground">
                Review spend and model activity for the selected workspace.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Select
                value={rangeKey}
                onValueChange={(value) => setRangeKey(value as RangeKey)}
              >
                <SelectTrigger className="min-w-36 bg-card">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="7d">Last 7 days</SelectItem>
                  <SelectItem value="30d">Last 30 days</SelectItem>
                  <SelectItem value="90d">Last 90 days</SelectItem>
                </SelectContent>
              </Select>
              <Button
                variant="outline"
                size="icon"
                aria-label="Refresh usage"
                onClick={() => void usage.refetch()}
              >
                <RefreshCw className={usage.isFetching ? "animate-spin" : ""} />
              </Button>
            </div>
          </div>

          {usage.isError ? (
            <div className="mb-6 rounded-lg border border-destructive/25 bg-destructive/5 px-4 py-3 text-sm text-destructive">
              {usage.error.message}
            </div>
          ) : null}

          <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_280px]">
            <Card className="overflow-hidden shadow-sm">
              <CardHeader className="flex-row items-start justify-between gap-4 border-b p-5">
                <div>
                  <CardTitle className="text-base">
                    Activity over time
                  </CardTitle>
                  <CardDescription className="mt-1">
                    Daily totals for the selected period.
                  </CardDescription>
                </div>
                <div className="flex rounded-md bg-muted p-0.5">
                  {(["cost", "tokens", "requests"] as const).map((value) => (
                    <button
                      key={value}
                      type="button"
                      onClick={() => setMetric(value)}
                      className={`rounded px-2.5 py-1.5 text-xs font-medium capitalize transition-colors ${
                        metric === value
                          ? "bg-card text-foreground shadow-sm"
                          : "text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      {value}
                    </button>
                  ))}
                </div>
              </CardHeader>
              <CardContent className="p-5">
                {usage.isLoading ? (
                  <div className="grid h-[330px] place-items-center">
                    <LoaderCircle className="size-5 animate-spin text-muted-foreground" />
                  </div>
                ) : (
                  <ChartContainer
                    config={chartConfig}
                    className="h-[330px] w-full"
                  >
                    <AreaChart
                      data={chartData}
                      margin={{ left: 4, right: 8, top: 12 }}
                    >
                      <defs>
                        <linearGradient
                          id="usage-area"
                          x1="0"
                          y1="0"
                          x2="0"
                          y2="1"
                        >
                          <stop
                            offset="5%"
                            stopColor={`var(--color-${metric})`}
                            stopOpacity={0.28}
                          />
                          <stop
                            offset="95%"
                            stopColor={`var(--color-${metric})`}
                            stopOpacity={0.02}
                          />
                        </linearGradient>
                      </defs>
                      <CartesianGrid vertical={false} />
                      <XAxis
                        dataKey="date"
                        axisLine={false}
                        tickLine={false}
                        minTickGap={32}
                        tickFormatter={formatDate}
                      />
                      <YAxis
                        axisLine={false}
                        tickLine={false}
                        width={52}
                        tickFormatter={(value: number) =>
                          metric === "cost"
                            ? formatUsd(value)
                            : compactNumber(value)
                        }
                      />
                      <ChartTooltip
                        content={
                          <ChartTooltipContent
                            labelFormatter={(label) =>
                              formatDate(String(label))
                            }
                            valueFormatter={(value) =>
                              metric === "cost"
                                ? formatUsd(Number(value))
                                : Number(value).toLocaleString()
                            }
                          />
                        }
                      />
                      <Area
                        type="monotone"
                        dataKey={metric}
                        stroke={`var(--color-${metric})`}
                        strokeWidth={2}
                        fill="url(#usage-area)"
                        activeDot={{ r: 4 }}
                      />
                    </AreaChart>
                  </ChartContainer>
                )}
              </CardContent>
            </Card>

            <Card className="divide-y shadow-sm">
              <SummaryMetric
                icon={<CircleDollarSign />}
                label="Total spend"
                value={formatNanoUsd(usage.data?.charge ?? "0")}
              />
              <SummaryMetric
                icon={<Sigma />}
                label="Total tokens"
                value={compactNumber(totalTokens.toString())}
                detail={`${compactNumber(usage.data?.input_tokens ?? "0")} input · ${compactNumber(usage.data?.output_tokens ?? "0")} output`}
              />
              <SummaryMetric
                icon={<Zap />}
                label="Requests"
                value={Number(
                  usage.data?.generation_count ?? 0,
                ).toLocaleString()}
                detail={
                  Number(usage.data?.generation_count ?? 0)
                    ? `${successRate.toFixed(1)}% succeeded`
                    : "No requests in this period"
                }
              />
            </Card>
          </div>

          <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1.35fr)_minmax(320px,.65fr)]">
            <Card className="shadow-sm">
              <CardHeader className="flex-row items-start justify-between gap-4 border-b p-5">
                <div>
                  <CardTitle className="text-base">Spend by model</CardTitle>
                  <CardDescription className="mt-1">
                    Model share for this period.
                  </CardDescription>
                </div>
                <Button asChild variant="ghost" size="sm">
                  <Link to="/logs">
                    View logs <ArrowRight />
                  </Link>
                </Button>
              </CardHeader>
              <CardContent className="p-5">
                {usage.data?.models.length ? (
                  <ChartContainer
                    config={modelChartConfig}
                    className="h-[260px] w-full"
                  >
                    <BarChart
                      data={usage.data.models.map((model) => ({
                        model: model.model_id,
                        cost: Number(model.charge) / 1_000_000_000,
                      }))}
                      layout="vertical"
                      margin={{ left: 16, right: 24 }}
                    >
                      <CartesianGrid horizontal={false} />
                      <XAxis
                        type="number"
                        axisLine={false}
                        tickLine={false}
                        tickFormatter={(value) => formatUsd(Number(value))}
                      />
                      <YAxis
                        dataKey="model"
                        type="category"
                        axisLine={false}
                        tickLine={false}
                        width={130}
                        tickFormatter={(value: string) =>
                          value.length > 20 ? `${value.slice(0, 19)}…` : value
                        }
                      />
                      <ChartTooltip
                        content={
                          <ChartTooltipContent
                            hideLabel
                            valueFormatter={(value) => formatUsd(Number(value))}
                          />
                        }
                      />
                      <Bar
                        dataKey="cost"
                        fill="var(--color-cost)"
                        radius={[0, 4, 4, 0]}
                      />
                    </BarChart>
                  </ChartContainer>
                ) : (
                  <EmptyUsage />
                )}
              </CardContent>
            </Card>

            <Card className="shadow-sm">
              <CardHeader className="border-b p-5">
                <CardTitle className="text-base">Token distribution</CardTitle>
                <CardDescription>Input and output share.</CardDescription>
              </CardHeader>
              <CardContent className="p-5">
                {totalTokens > 0n ? (
                  <div className="space-y-6">
                    <div className="flex h-3 overflow-hidden rounded-full bg-muted">
                      <span
                        className="bg-primary"
                        style={{
                          width: `${(Number(usage.data?.input_tokens ?? 0) / Number(totalTokens)) * 100}%`,
                        }}
                      />
                      <span className="flex-1 bg-[#b6cf5a]" />
                    </div>
                    <TokenRow
                      label="Input"
                      value={usage.data?.input_tokens ?? "0"}
                      color="bg-primary"
                    />
                    <TokenRow
                      label="Output"
                      value={usage.data?.output_tokens ?? "0"}
                      color="bg-[#b6cf5a]"
                    />
                  </div>
                ) : (
                  <EmptyUsage />
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </main>
    </AppShell>
  );
};

const SummaryMetric = ({
  icon,
  label,
  value,
  detail,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  detail?: string;
}) => (
  <div className="p-5">
    <div className="flex items-center gap-2 text-xs text-muted-foreground [&_svg]:size-4">
      {icon}
      {label}
    </div>
    <p className="mt-3 text-2xl font-semibold tracking-[-0.035em]">{value}</p>
    {detail ? (
      <p className="mt-1 text-xs text-muted-foreground">{detail}</p>
    ) : null}
  </div>
);

const TokenRow = ({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color: string;
}) => (
  <div className="flex items-center justify-between gap-4 text-sm">
    <span className="flex items-center gap-2 text-muted-foreground">
      <span className={`size-2 rounded-sm ${color}`} />
      {label}
    </span>
    <span className="font-medium tabular-nums">
      {Number(value).toLocaleString()}
    </span>
  </div>
);

const EmptyUsage = () => (
  <div className="grid min-h-52 place-items-center text-center">
    <div>
      <ChartNoAxesCombined className="mx-auto size-5 text-muted-foreground" />
      <p className="mt-3 text-sm font-medium">No usage in this period</p>
      <p className="mt-1 text-xs text-muted-foreground">
        Activity will appear after the first request.
      </p>
    </div>
  </div>
);
