import {
  Children,
  createContext,
  isValidElement,
  useContext,
  useState,
  type ReactElement,
  type ReactNode,
} from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  XAxis,
  YAxis,
} from "recharts";
import {
  ChevronDown,
  CircleCheck,
  FileWarning,
  Info,
  Lightbulb,
  TriangleAlert,
} from "lucide-react";

import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { ReportRow } from "@/lib/report-data";
import { cn } from "@/lib/utils";

export type ReportDataset =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; rows: ReportRow[] };

export const ReportDataContext = createContext<
  ReadonlyMap<string, ReportDataset>
>(new Map());

const SERIES_COLORS = ["#6e7f31", "#3f6d8f", "#171714", "#b7791f", "#8a8779"];

const TONES = {
  positive: "text-[#4f5c22]",
  negative: "text-[#9a5b0f]",
  neutral: "text-muted-foreground",
} as const;
type Tone = keyof typeof TONES;

const BADGE_TONES = {
  positive: "bg-[#e7ecd6] text-[#3d4a14]",
  negative: "bg-amber-100 text-amber-900",
  neutral: "bg-muted text-foreground/80",
  info: "bg-[#dfe8f0] text-[#24435a]",
} as const;

const toneClass = (tone: unknown) => TONES[tone as Tone] ?? TONES.neutral;

const columnLabel = (key: string) => {
  const words = key.replace(/[_-]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
};

const strings = (value: unknown) =>
  Array.isArray(value) ? value.map(String) : [];

const numeric = (value: unknown) =>
  typeof value === "number" ? value : Number(value ?? Number.NaN);

const formatValue = (value: unknown, format: unknown) => {
  const number = numeric(value);
  if (!Number.isFinite(number)) return String(value ?? "—");
  if (format === "percent")
    return `${(number <= 1 ? number * 100 : number).toLocaleString(undefined, {
      maximumFractionDigits: 1,
    })}%`;
  if (format === "usd")
    return number.toLocaleString(undefined, {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: number < 1 ? 4 : 2,
    });

  return number.toLocaleString(undefined, { maximumFractionDigits: 2 });
};

const useDataset = (name: unknown): ReportDataset =>
  useContext(ReportDataContext).get(String(name)) ?? { status: "loading" };

const DatasetState = ({
  dataset,
  name,
  height = "h-48",
}: {
  dataset: ReportDataset;
  name: unknown;
  height?: string;
}) =>
  dataset.status === "loading" ? (
    <Skeleton className={cn(height, "w-full")} />
  ) : dataset.status === "error" ? (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-1.5 rounded-lg bg-muted/50 px-4 text-center",
        height,
      )}
    >
      <FileWarning aria-hidden className="size-4 text-muted-foreground" />
      <p className="text-sm text-muted-foreground">
        This data isn’t available yet.
      </p>
      <p className="font-mono text-xs text-muted-foreground/80">
        {String(name)}
      </p>
    </div>
  ) : null;

const Figure = ({
  title,
  caption,
  children,
}: {
  title?: unknown;
  caption?: unknown;
  children: ReactNode;
}) => (
  <figure className="flex min-w-0 flex-col gap-3 rounded-xl border bg-card px-5 py-4">
    {title || caption ? (
      <figcaption className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        {title ? (
          <span className="font-semibold">{String(title)}</span>
        ) : (
          <span />
        )}
        {caption ? (
          <span className="text-xs text-muted-foreground">
            {String(caption)}
          </span>
        ) : null}
      </figcaption>
    ) : null}
    {children}
  </figure>
);

const Legend = ({ keys, config }: { keys: string[]; config: ChartConfig }) =>
  keys.length > 1 ? (
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
      {keys.map((key) => (
        <span key={key} className="flex items-center gap-1.5">
          <span
            aria-hidden
            className="size-2 rounded-[2px]"
            style={{ background: config[key]?.color }}
          />
          {columnLabel(key)}
        </span>
      ))}
    </div>
  ) : null;

const seriesConfig = (keys: string[]) =>
  Object.fromEntries(
    keys.map((key, index) => [
      key,
      {
        label: columnLabel(key),
        color: SERIES_COLORS[index % SERIES_COLORS.length]!,
      },
    ]),
  ) satisfies ChartConfig;

export const MetricGrid = ({ children }: { children: ReactNode }) => (
  <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">{children}</div>
);

const Sparkline = ({ data, y }: { data: unknown; y: unknown }) => {
  const dataset = useDataset(data);
  if (dataset.status !== "ready" || !y) return null;

  const key = String(y);
  return (
    <ChartContainer
      config={{ [key]: { label: key, color: SERIES_COLORS[0]! } }}
      className="-mx-1 mt-1 aspect-auto h-8 w-[calc(100%+0.5rem)]"
    >
      <LineChart data={dataset.rows}>
        <Line
          dataKey={key}
          type="monotone"
          stroke={`var(--color-${key})`}
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ChartContainer>
  );
};

export const Metric = ({
  label,
  value,
  change,
  tone,
  data,
  y,
}: {
  label: string;
  value: string;
  change?: string;
  tone?: Tone;
  data?: string;
  y?: string;
}) => (
  <div className="flex min-w-0 flex-col gap-1.5 rounded-xl border bg-card px-4 py-3.5">
    <span className="text-xs text-muted-foreground">{label}</span>
    <span className="text-xl font-semibold tracking-tight tabular-nums">
      {value}
    </span>
    {change ? (
      <span className={cn("text-xs", toneClass(tone ?? "positive"))}>
        {change}
      </span>
    ) : null}
    {data ? <Sparkline data={data} y={y} /> : null}
  </div>
);

const CALLOUTS = {
  note: { icon: Info, className: "bg-muted/60", label: "Note" },
  recommendation: {
    icon: Lightbulb,
    className: "bg-[#eef1e3] text-[#26300c]",
    label: "Recommendation",
  },
  success: {
    icon: CircleCheck,
    className: "bg-[#e7ecd6] text-[#26300c]",
    label: "Result",
  },
  warning: {
    icon: TriangleAlert,
    className: "bg-amber-50 text-amber-950",
    label: "Warning",
  },
} as const;

export const Callout = ({
  type,
  title,
  children,
}: {
  type?: keyof typeof CALLOUTS;
  title?: string;
  children: ReactNode;
}) => {
  const callout = CALLOUTS[type ?? "note"] ?? CALLOUTS.note;
  const Icon = callout.icon;

  return (
    <aside
      className={cn(
        "flex flex-col gap-2 rounded-xl px-5 py-4 [&>p]:my-0",
        callout.className,
      )}
    >
      <span className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide">
        <Icon aria-hidden className="size-3.5" />
        {title ?? callout.label}
      </span>
      {children}
    </aside>
  );
};

export const Columns = ({
  count,
  children,
}: {
  count?: number;
  children: ReactNode;
}) => (
  <div
    className={cn(
      "grid gap-3",
      count === 3
        ? "sm:grid-cols-3"
        : count === 4
          ? "sm:grid-cols-2 lg:grid-cols-4"
          : "sm:grid-cols-2",
    )}
  >
    {children}
  </div>
);

export const Card = ({
  title,
  children,
}: {
  title?: string;
  children: ReactNode;
}) => (
  <section className="flex min-w-0 flex-col gap-2 rounded-xl border bg-card px-5 py-4 [&>ol]:my-0 [&>p]:my-0 [&>ul]:my-0">
    {title ? <h4 className="font-semibold">{title}</h4> : null}
    {children}
  </section>
);

export const Badge = ({
  tone,
  children,
}: {
  tone?: keyof typeof BADGE_TONES;
  children: ReactNode;
}) => (
  <span
    className={cn(
      "inline-flex items-center rounded-full px-2 py-0.5 align-middle text-xs font-medium leading-5",
      BADGE_TONES[tone ?? "neutral"] ?? BADGE_TONES.neutral,
    )}
  >
    {children}
  </span>
);

export const ReportChart = ({
  type,
  data,
  x,
  y,
  stacked,
  format,
  title,
  caption,
}: {
  type: "bar" | "line" | "area" | "donut";
  data: string;
  x: string;
  y: string[];
  stacked?: boolean;
  format?: "percent" | "usd" | "number";
  title?: string;
  caption?: string;
}) => {
  const dataset = useDataset(data);
  const series = strings(y);
  const config = seriesConfig(series);
  const tick = (value: unknown) => formatValue(value, format);
  const axes = [
    <CartesianGrid key="grid" vertical={false} />,
    <XAxis
      key="x"
      dataKey={String(x)}
      tickLine={false}
      axisLine={false}
      tickMargin={8}
    />,
    <YAxis
      key="y"
      tickLine={false}
      axisLine={false}
      width={44}
      tickFormatter={tick}
    />,
    <ChartTooltip
      key="tooltip"
      content={<ChartTooltipContent valueFormatter={tick} />}
    />,
  ];

  if (type === "donut") {
    const key = series[0] ?? "";
    const rows =
      dataset.status === "ready"
        ? dataset.rows.map((row) => ({
            name: String(row[String(x)] ?? ""),
            value: numeric(row[key]),
          }))
        : [];
    const total = rows.reduce(
      (sum, row) => sum + (Number.isFinite(row.value) ? row.value : 0),
      0,
    );

    return (
      <Figure title={title} caption={caption}>
        {dataset.status === "ready" ? (
          <div className="flex flex-wrap items-center gap-6">
            <ChartContainer config={{}} className="aspect-square h-40">
              <PieChart>
                <ChartTooltip content={<ChartTooltipContent hideLabel />} />
                <Pie
                  data={rows}
                  dataKey="value"
                  nameKey="name"
                  innerRadius="62%"
                  strokeWidth={2}
                >
                  {rows.map((row, index) => (
                    <Cell
                      key={row.name}
                      fill={SERIES_COLORS[index % SERIES_COLORS.length]!}
                    />
                  ))}
                </Pie>
              </PieChart>
            </ChartContainer>
            <ul className="flex min-w-48 flex-1 flex-col gap-2 text-sm">
              {rows.map((row, index) => (
                <li key={row.name} className="flex items-center gap-2.5">
                  <span
                    aria-hidden
                    className="size-2.5 shrink-0 rounded-[3px]"
                    style={{
                      background: SERIES_COLORS[index % SERIES_COLORS.length],
                    }}
                  />
                  <span className="min-w-0 flex-1 truncate">{row.name}</span>
                  <span className="tabular-nums text-muted-foreground">
                    {formatValue(row.value, format)}
                    {total > 0 && format !== "percent"
                      ? ` · ${Math.round((row.value / total) * 100)}%`
                      : ""}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <DatasetState dataset={dataset} name={data} />
        )}
      </Figure>
    );
  }

  return (
    <Figure title={title} caption={caption}>
      <Legend keys={series} config={config} />
      {dataset.status === "ready" ? (
        <ChartContainer config={config} className="aspect-auto h-60 w-full">
          {type === "bar" ? (
            <BarChart data={dataset.rows}>
              {axes}
              {series.map((key, index) => (
                <Bar
                  key={key}
                  dataKey={key}
                  fill={`var(--color-${key})`}
                  radius={
                    stacked && index < series.length - 1 ? 0 : [4, 4, 0, 0]
                  }
                  {...(stacked ? { stackId: "stack" } : {})}
                />
              ))}
            </BarChart>
          ) : type === "area" ? (
            <AreaChart data={dataset.rows}>
              {axes}
              {series.map((key) => (
                <Area
                  key={key}
                  dataKey={key}
                  type="monotone"
                  stroke={`var(--color-${key})`}
                  fill={`var(--color-${key})`}
                  fillOpacity={stacked ? 0.5 : 0.15}
                  {...(stacked ? { stackId: "stack" } : {})}
                />
              ))}
            </AreaChart>
          ) : (
            <LineChart data={dataset.rows}>
              {axes}
              {series.map((key) => (
                <Line
                  key={key}
                  dataKey={key}
                  type="monotone"
                  stroke={`var(--color-${key})`}
                  strokeWidth={2}
                  dot={false}
                />
              ))}
            </LineChart>
          )}
        </ChartContainer>
      ) : (
        <DatasetState dataset={dataset} name={data} height="h-60" />
      )}
    </Figure>
  );
};

export const BarList = ({
  data,
  label,
  value,
  format,
  max,
  title,
  caption,
}: {
  data: string;
  label: string;
  value: string;
  format?: "percent" | "usd" | "number";
  max?: number;
  title?: string;
  caption?: string;
}) => {
  const dataset = useDataset(data);
  const rows =
    dataset.status === "ready"
      ? dataset.rows
          .map((row) => ({
            label: String(row[String(label)] ?? ""),
            value: numeric(row[String(value)]),
          }))
          .filter((row) => Number.isFinite(row.value))
      : [];
  const ceiling =
    max ??
    (format === "percent"
      ? rows.some((row) => row.value > 1)
        ? 100
        : 1
      : Math.max(...rows.map((row) => row.value), 0));

  return (
    <Figure title={title} caption={caption}>
      {dataset.status === "ready" ? (
        <ul className="flex flex-col gap-2.5">
          {rows.map((row) => (
            <li
              key={row.label}
              className="grid grid-cols-[minmax(5rem,8rem)_minmax(0,1fr)_3.5rem] items-center gap-3 text-sm"
            >
              <span className="truncate text-foreground/80">{row.label}</span>
              <span className="h-2 overflow-hidden rounded-full bg-muted">
                <span
                  className="block h-full rounded-full bg-[#6e7f31]"
                  style={{
                    width: `${ceiling > 0 ? Math.min(100, (row.value / ceiling) * 100) : 0}%`,
                  }}
                />
              </span>
              <span className="text-right tabular-nums">
                {formatValue(row.value, format)}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <DatasetState dataset={dataset} name={data} height="h-32" />
      )}
    </Figure>
  );
};

export const Heatmap = ({
  data,
  row,
  column,
  value,
  title,
  caption,
}: {
  data: string;
  row: string;
  column: string;
  value: string;
  title?: string;
  caption?: string;
}) => {
  const dataset = useDataset(data);
  const cells =
    dataset.status === "ready"
      ? dataset.rows.map((entry) => ({
          row: String(entry[String(row)] ?? ""),
          column: String(entry[String(column)] ?? ""),
          value: numeric(entry[String(value)]),
        }))
      : [];
  const rows = [...new Set(cells.map((cell) => cell.row))];
  const columns = [...new Set(cells.map((cell) => cell.column))];
  if (rows.length > 50 || columns.length > 50)
    return (
      <Figure title={title} caption={caption}>
        <DatasetState
          dataset={{
            status: "error",
            message: "Heatmaps are limited to 50 rows and 50 columns.",
          }}
          name={data}
        />
      </Figure>
    );

  const peak = Math.max(
    ...cells.map((cell) => (Number.isFinite(cell.value) ? cell.value : 0)),
    1,
  );

  return (
    <Figure title={title} caption={caption}>
      {dataset.status === "ready" ? (
        <div className="overflow-x-auto">
          <table className="w-full border-separate border-spacing-1 text-xs">
            <thead>
              <tr>
                <th className="text-left font-normal text-muted-foreground">
                  {columnLabel(String(row))} ↓ · {columnLabel(String(column))} →
                </th>
                {columns.map((name) => (
                  <th
                    key={name}
                    className="px-1 text-center font-medium text-muted-foreground"
                  >
                    {name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((name) => (
                <tr key={name}>
                  <th className="pr-2 text-left font-medium text-muted-foreground">
                    {name}
                  </th>
                  {columns.map((other) => {
                    const cell = cells.find(
                      (entry) => entry.row === name && entry.column === other,
                    );
                    const strength =
                      cell && Number.isFinite(cell.value)
                        ? cell.value / peak
                        : 0;

                    return (
                      <td
                        key={other}
                        className="h-10 min-w-12 rounded-md text-center tabular-nums"
                        style={{
                          background: `rgb(110 127 49 / ${0.08 + strength * 0.85})`,
                          color: strength > 0.55 ? "#fffffe" : undefined,
                        }}
                      >
                        {cell ? formatValue(cell.value, "number") : ""}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <DatasetState dataset={dataset} name={data} />
      )}
    </Figure>
  );
};

export const DataTable = ({
  data,
  columns,
  title,
  caption,
  limit,
}: {
  data: string;
  columns?: string[];
  title?: string;
  caption?: string;
  limit?: number;
}) => {
  const dataset = useDataset(data);
  const rows = dataset.status === "ready" ? dataset.rows : [];
  const keys = Array.isArray(columns)
    ? columns.map(String)
    : Object.keys(rows[0] ?? {});
  const shown =
    typeof limit === "number" && limit > 0
      ? Math.min(Math.floor(limit), 500)
      : 50;

  return (
    <Figure title={title} caption={caption}>
      {dataset.status === "ready" ? (
        <div className="-mx-5 overflow-x-auto">
          <Table className="min-w-[32rem]">
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                {keys.map((key) => (
                  <TableHead key={key} className="first:pl-5 last:pr-5">
                    {columnLabel(key)}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.slice(0, shown).map((row, index) => (
                <TableRow key={index}>
                  {keys.map((key) => (
                    <TableCell
                      key={key}
                      className="whitespace-normal align-top first:pl-5 last:pr-5"
                    >
                      {row[key] ?? "—"}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {rows.length > shown ? (
            <p className="px-5 pt-3 text-xs text-muted-foreground">
              Showing {shown} of {rows.length.toLocaleString()} rows. Download{" "}
              {String(data)} for the rest.
            </p>
          ) : null}
        </div>
      ) : (
        <DatasetState dataset={dataset} name={data} />
      )}
    </Figure>
  );
};

const VERDICTS = {
  better: { label: "Better", tone: "positive" },
  same: { label: "Same", tone: "neutral" },
  worse: { label: "Worse", tone: "negative" },
} as const;

export const Comparison = ({
  title,
  verdict,
  children,
}: {
  title?: string;
  verdict?: keyof typeof VERDICTS;
  children: ReactNode;
}) => {
  const outcome = verdict ? VERDICTS[verdict] : undefined;

  return (
    <section className="flex min-w-0 flex-col gap-3 rounded-xl border bg-card px-5 py-4">
      {title || outcome ? (
        <div className="flex flex-wrap items-start justify-between gap-3">
          {title ? <p className="font-medium">{title}</p> : <span />}
          {outcome ? <Badge tone={outcome.tone}>{outcome.label}</Badge> : null}
        </div>
      ) : null}
      <div className="grid gap-3 sm:grid-cols-2">{children}</div>
    </section>
  );
};

export const Side = ({
  title,
  children,
}: {
  title?: string;
  children: ReactNode;
}) => (
  <div className="flex min-w-0 flex-col gap-1.5 rounded-lg bg-muted/50 px-4 py-3 [&>p]:my-0 [&>pre]:my-0">
    {title ? (
      <span className="text-xs font-medium text-muted-foreground">{title}</span>
    ) : null}
    {children}
  </div>
);

export const Facts = ({ children }: { children: ReactNode }) => (
  <dl className="grid gap-x-8 gap-y-3 rounded-xl border bg-card px-5 py-4 sm:grid-cols-2">
    {children}
  </dl>
);

export const Fact = ({ label, value }: { label: string; value: string }) => (
  <div className="flex items-baseline justify-between gap-4 border-b border-border/60 pb-2 text-sm">
    <dt className="text-muted-foreground">{label}</dt>
    <dd className="min-w-0 truncate text-right font-medium">{value}</dd>
  </div>
);

export const Timeline = ({ children }: { children: ReactNode }) => (
  <ol className="flex flex-col">{children}</ol>
);

export const TimelineEvent = ({
  date,
  title,
  children,
}: {
  date?: string;
  title: string;
  children: ReactNode;
}) => (
  <li className="group/event grid grid-cols-[5.5rem_1rem_minmax(0,1fr)] gap-3 pb-5 last:pb-0">
    <span className="pt-0.5 text-xs text-muted-foreground tabular-nums">
      {date}
    </span>
    <span className="relative flex justify-center">
      <span className="z-10 mt-1.5 size-2.5 rounded-full bg-[#6e7f31] ring-4 ring-background" />
      <span
        aria-hidden
        className="absolute top-4 -bottom-5 w-px bg-border group-last/event:hidden"
      />
    </span>
    <div className="flex min-w-0 flex-col gap-1 [&>p]:my-0">
      <span className="font-medium">{title}</span>
      {children}
    </div>
  </li>
);

export const Details = ({
  summary,
  children,
}: {
  summary: string;
  children: ReactNode;
}) => (
  <details className="group rounded-xl border bg-card px-5 py-3 [&_p]:my-0">
    <summary className="flex cursor-pointer list-none items-center justify-between gap-3 font-medium [&::-webkit-details-marker]:hidden">
      {summary}
      <ChevronDown
        aria-hidden
        className="size-4 text-muted-foreground transition-transform group-open:rotate-180"
      />
    </summary>
    <div className="mt-3 flex flex-col gap-3 border-t pt-3">{children}</div>
  </details>
);

export const Tab = ({ children }: { title: string; children: ReactNode }) => (
  <>{children}</>
);

export const Tabs = ({ children }: { children: ReactNode }) => {
  const tabs = Children.toArray(children).filter(
    (child): child is ReactElement<{ title?: string; children?: ReactNode }> =>
      isValidElement(child),
  );
  const [active, setActive] = useState(0);
  const current = tabs[Math.min(active, tabs.length - 1)];

  return (
    <div className="flex min-w-0 flex-col gap-4">
      <div role="tablist" className="flex flex-wrap gap-1 border-b">
        {tabs.map((tab, index) => (
          <button
            key={index}
            type="button"
            role="tab"
            aria-selected={index === active}
            onClick={() => setActive(index)}
            className={cn(
              "-mb-px inline-flex h-10 items-center border-b-2 px-3 text-sm font-medium transition-colors",
              index === active
                ? "border-foreground text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {tab.props.title ?? `Tab ${index + 1}`}
          </button>
        ))}
      </div>
      <div role="tabpanel" className="flex min-w-0 flex-col gap-4">
        {current?.props.children}
      </div>
    </div>
  );
};
