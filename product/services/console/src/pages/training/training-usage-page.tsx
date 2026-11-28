import { Link } from "@tanstack/react-router";
import { ChartNoAxesCombined, LoaderCircle, RefreshCw } from "lucide-react";
import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";

import { OptionSelect } from "@/components/option-select";
import { SectionCard, Stat, StatGrid } from "@/components/training/training-ui";
import { Button } from "@/components/ui/button";
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useUsageSummary } from "@/hooks/use-grad";
import { useProductContext } from "@/hooks/use-product-context";
import { formatCost, formatTokens } from "@/lib/grad/format";
import { RECIPE_LABEL } from "@/lib/grad/labels";
import type { RecipeKind } from "@/lib/grad/types";
import {
  USAGE_GROUP_OPTIONS,
  USAGE_KIND_LABEL,
  USAGE_RANGE_OPTIONS,
  isTimeGroup,
  usageRange,
  type UsageGroupBy,
  type UsageKind,
  type UsageRangeKey,
  type UsageSummary,
} from "@/lib/grad/usage";
import { ConsolePage, LoadFailed } from "@/pages/console-page";

const chartConfig = {
  cost: { label: "Cost", color: "#171714" },
} satisfies ChartConfig;

const groupLabel = (groupBy: UsageGroupBy, key: string | null) => {
  if (key === null) return "No recipe";
  if (groupBy === "kind") return USAGE_KIND_LABEL[key as UsageKind] ?? key;
  if (groupBy === "recipe") return RECIPE_LABEL[key as RecipeKind] ?? key;
  if (isTimeGroup(groupBy))
    return new Date(`${key}T00:00:00Z`).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      timeZone: "UTC",
    });

  return key;
};

export const TrainingUsagePage = () => {
  const { workspaceId } = useProductContext();

  return <TrainingUsageBody key={workspaceId} />;
};

const TrainingUsageBody = () => {
  const [rangeKey, setRangeKey] = useState<UsageRangeKey>("month");
  const [groupBy, setGroupBy] = useState<UsageGroupBy>("day");
  const range = useMemo(() => usageRange(rangeKey, new Date()), [rangeKey]);
  const usage = useUsageSummary(range, groupBy);

  return (
    <ConsolePage
      page="training"
      title="Training usage"
      description="Spend on training runs, evals, scoring and labeling in this workspace."
      width="wide"
      actions={
        <>
          <OptionSelect
            label="Usage time range"
            value={rangeKey}
            options={USAGE_RANGE_OPTIONS}
            onValueChange={setRangeKey}
            className="min-w-36 bg-card"
          />
          <Button
            variant="outline"
            size="icon"
            aria-label="Refresh usage"
            onClick={() => void usage.refetch()}
          >
            <RefreshCw className={usage.isFetching ? "animate-spin" : ""} />
          </Button>
        </>
      }
    >
      {usage.isError ? (
        <LoadFailed
          subject="usage"
          retrying={usage.isFetching}
          onRetry={() => void usage.refetch()}
          className="min-h-80 rounded-xl border bg-card"
        />
      ) : usage.isPending ? (
        <div className="grid min-h-80 place-items-center rounded-xl border bg-card">
          <LoaderCircle
            aria-label="Loading usage"
            className="size-5 animate-spin text-muted-foreground"
          />
        </div>
      ) : (
        <UsageBody
          summary={usage.data}
          groupBy={groupBy}
          onGroupBy={setGroupBy}
        />
      )}
    </ConsolePage>
  );
};

const UsageBody = ({
  summary,
  groupBy,
  onGroupBy,
}: {
  summary: UsageSummary;
  groupBy: UsageGroupBy;
  onGroupBy: (groupBy: UsageGroupBy) => void;
}) => {
  const training = summary.byKind.find((kind) => kind.kind === "training");
  const data = summary.groups.map((group) => ({
    label: groupLabel(groupBy, group.key),
    cost: group.costUsd,
  }));
  const vertical = !isTimeGroup(groupBy);

  return (
    <div className="space-y-5">
      <StatGrid>
        <Stat label="Total spend" value={formatCost(summary.costUsd)} />
        <Stat label="Tokens" value={formatTokens(summary.tokens)} />
        <Stat
          label="Training"
          value={formatCost(training?.costUsd ?? 0)}
          detail={`${formatTokens(training?.tokens ?? 0)} tokens`}
        />
        <Stat
          label="Evals and labeling"
          value={formatCost(summary.costUsd - (training?.costUsd ?? 0))}
        />
      </StatGrid>

      <SectionCard
        title="Spend"
        description={
          USAGE_GROUP_OPTIONS.find((option) => option.value === groupBy)?.label
        }
        actions={
          <OptionSelect
            label="Group usage"
            value={groupBy}
            options={USAGE_GROUP_OPTIONS}
            onValueChange={onGroupBy}
            className="min-w-32 bg-card"
          />
        }
      >
        {data.length ? (
          <ChartContainer config={chartConfig} className="h-[280px] w-full">
            <BarChart
              data={data}
              layout={vertical ? "vertical" : "horizontal"}
              margin={{ left: vertical ? 16 : 4, right: 16, top: 8 }}
            >
              <CartesianGrid vertical={vertical} horizontal={!vertical} />
              {vertical ? (
                <>
                  <XAxis
                    type="number"
                    axisLine={false}
                    tickLine={false}
                    tickFormatter={(value: number) => formatCost(value)}
                  />
                  <YAxis
                    dataKey="label"
                    type="category"
                    axisLine={false}
                    tickLine={false}
                    width={140}
                  />
                </>
              ) : (
                <>
                  <XAxis
                    dataKey="label"
                    axisLine={false}
                    tickLine={false}
                    minTickGap={24}
                  />
                  <YAxis
                    axisLine={false}
                    tickLine={false}
                    width={56}
                    tickFormatter={(value: number) => formatCost(value)}
                  />
                </>
              )}
              <ChartTooltip
                content={
                  <ChartTooltipContent
                    valueFormatter={(value) => formatCost(Number(value))}
                  />
                }
              />
              <Bar
                dataKey="cost"
                maxBarSize={vertical ? 28 : 40}
                fill="var(--color-cost)"
                radius={vertical ? [0, 4, 4, 0] : [4, 4, 0, 0]}
              />
            </BarChart>
          </ChartContainer>
        ) : (
          <div className="grid min-h-52 place-items-center text-center">
            <div>
              <ChartNoAxesCombined className="mx-auto size-5 text-muted-foreground" />
              <p className="mt-3 text-sm font-medium">
                No usage in this period
              </p>
            </div>
          </div>
        )}
      </SectionCard>

      <div className="grid gap-5 lg:grid-cols-2">
        <TopTable
          title="Top runs"
          rows={summary.topRuns}
          link={(id) => ({
            to: "/training/runs/$runId",
            params: { runId: id },
          })}
        />
        <TopTable
          title="Top evals and labeling"
          rows={summary.topEvals}
          link={(id) => ({
            to: "/training/evals/$evalId",
            params: { evalId: id },
          })}
        />
      </div>
    </div>
  );
};

const TopTable = ({
  title,
  rows,
  link,
}: {
  title: string;
  rows: UsageSummary["topRuns"];
  link: (
    id: string,
  ) =>
    | { to: "/training/runs/$runId"; params: { runId: string } }
    | { to: "/training/evals/$evalId"; params: { evalId: string } };
}) => (
  <SectionCard title={title} contentClassName="p-0">
    {rows.length ? (
      <Table>
        <TableHeader className="bg-muted/40">
          <TableRow className="hover:bg-transparent">
            <TableHead className="pl-5">Name</TableHead>
            <TableHead>Kind</TableHead>
            <TableHead className="text-right">Tokens</TableHead>
            <TableHead className="pr-5 text-right">Cost</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.id}>
              <TableCell className="pl-5 font-medium">
                <Link
                  {...link(row.id)}
                  className="underline-offset-4 hover:underline"
                >
                  {row.name ?? row.id}
                </Link>
              </TableCell>
              <TableCell className="text-muted-foreground">
                {USAGE_KIND_LABEL[row.kind]}
              </TableCell>
              <TableCell className="text-right tabular-nums text-muted-foreground">
                {formatTokens(row.tokens)}
              </TableCell>
              <TableCell className="pr-5 text-right tabular-nums">
                {formatCost(row.costUsd)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    ) : (
      <p className="p-5 text-sm text-muted-foreground">
        Nothing in this period.
      </p>
    )}
  </SectionCard>
);
