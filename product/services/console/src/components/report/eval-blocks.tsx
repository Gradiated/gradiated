import type { EvalMetric, EvalModel } from "@gradiated/contracts";
import { Search } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";

import { SegmentedControl } from "@/components/segmented-control";
import { Input } from "@/components/ui/input";
import {
  aggregate,
  formatDelta,
  formatMetric,
  groupCases,
  messageText,
  passedOf,
  pickMetric,
  pickModels,
  rolloutLabel,
  rolloutsOf,
  verdictOf,
  type EvalIndex,
  type Verdict,
} from "@/lib/eval-data";
import { cn } from "@/lib/utils";
import { useEvalDataset, useEvalPanel, type EvalView } from "./eval-context";
import { DatasetState, Figure } from "./report-blocks";

export const MODEL_COLORS = ["#6e7f31", "#3f6d8f"] as const;
const LIGHT_COLORS = ["#b9c58f", "#a3bccf"] as const;
const SAME_COLOR = "#e4e3dd";

type EvalProps = {
  eval: string;
  models?: string[];
  metric?: string;
  by?: string;
  title?: string;
  caption?: string;
};
type Ready = {
  file: string;
  view: EvalView;
  index: EvalIndex;
  a: EvalModel;
  b: EvalModel;
  metric: EvalMetric;
};

const EvalFigure = ({
  props,
  children,
}: {
  props: EvalProps;
  children: (ready: Ready) => ReactNode;
}) => {
  const dataset = useEvalDataset(props.eval);

  if (dataset.status !== "ready")
    return (
      <Figure title={props.title} caption={props.caption}>
        <DatasetState dataset={dataset} name={props.eval} />
      </Figure>
    );

  const [a, b] = pickModels(dataset.index, props.models);
  const metric = pickMetric(dataset.index, props.metric);
  return (
    <Figure title={props.title} caption={props.caption}>
      {children({
        file: props.eval,
        index: dataset.index,
        a: a!,
        b: b!,
        metric,
        view: { models: [a!.id, b!.id], metric: metric.id },
      })}
    </Figure>
  );
};

const Swatch = ({ color }: { color: string }) => (
  <span
    aria-hidden
    className="inline-block size-2.5 shrink-0 rounded-sm"
    style={{ background: color }}
  />
);

const Legend = ({ items }: { items: [string, string][] }) => (
  <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
    {items.map(([color, label]) => (
      <span key={label} className="inline-flex items-center gap-1.5">
        <Swatch color={color} />
        {label}
      </span>
    ))}
  </div>
);

const GroupRow = ({
  label,
  count,
  children,
}: {
  label: string;
  count: number;
  children: ReactNode;
}) => (
  <div className="grid grid-cols-[minmax(6rem,10rem)_minmax(0,1fr)] items-center gap-3">
    <span className="flex flex-col text-sm leading-5">
      {label}
      <span className="text-xs text-muted-foreground">{count} cases</span>
    </span>
    {children}
  </div>
);

const withAll = (index: EvalIndex, by?: string) => [
  { label: "All cases", ids: index.cases.map((item) => item.id) },
  ...groupCases(index, by),
];

// Mulberry32: a seeded generator keeps the interval stable between renders.
const seeded = (seed: number) => () => {
  seed = (seed + 0x6d2b79f5) | 0;
  let value = Math.imul(seed ^ (seed >>> 15), 1 | seed);
  value = (value + Math.imul(value ^ (value >>> 7), 61 | value)) ^ value;
  return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
};

// Resamples whole interval_group_by groups (cases without the tag stand alone),
// because rollouts of one case or one project are not independent.
const differenceInterval = ({ index, a, b, metric }: Ready) => {
  const key = index.eval.interval_group_by;
  const groups = [
    ...(key ? groupCases(index, key).map((group) => group.ids) : []),
    ...index.cases
      .filter((item) => !key || item.tags[key] === undefined)
      .map((item) => [item.id]),
  ];
  const totals = groups.map((ids) => ({
    a: aggregate(index, a.id, metric, ids),
    b: aggregate(index, b.id, metric, ids),
  }));
  const next = seeded(7);
  const deltas: number[] = [];

  for (let draw = 0; draw < 2000; draw++) {
    let sumA = 0;
    let countA = 0;
    let sumB = 0;
    let countB = 0;
    for (let pick = 0; pick < totals.length; pick++) {
      const total = totals[Math.floor(next() * totals.length)]!;
      sumA += (total.a.mean ?? 0) * total.a.n;
      countA += total.a.n;
      sumB += (total.b.mean ?? 0) * total.b.n;
      countB += total.b.n;
    }

    if (countA && countB)
      deltas.push(
        (sumA / countA - sumB / countB) * (metric.higher_is_better ? 1 : -1),
      );
  }

  deltas.sort((left, right) => left - right);
  return deltas.length
    ? {
        low: deltas[Math.floor(deltas.length * 0.025)]!,
        high: deltas[Math.floor(deltas.length * 0.975)]!,
      }
    : null;
};

const Stat = ({
  label,
  value,
  note,
}: {
  label: ReactNode;
  value: string;
  note?: string;
}) => (
  <div className="flex min-w-0 flex-col gap-1">
    <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
      {label}
    </span>
    <span className="text-2xl font-semibold tracking-tight tabular-nums">
      {value}
    </span>
    {note ? (
      <span className="text-xs text-muted-foreground">{note}</span>
    ) : null}
  </div>
);

const Summary = (ready: Ready) => {
  const { index, a, b, metric } = ready;
  const left = aggregate(index, a.id, metric);
  const right = aggregate(index, b.id, metric);
  const direction = metric.higher_is_better ? 1 : -1;
  const delta =
    left.mean !== null && right.mean !== null
      ? (left.mean - right.mean) * direction
      : null;
  const interval = differenceInterval(ready);
  const clear = interval && (interval.low > 0 || interval.high < 0);
  const incomplete = left.incomplete + right.incomplete;
  const verb = metric.kind === "pass" ? "passes" : "averages";
  const of = metric.kind === "pass" ? " of rollouts" : "";
  const note = (model: EvalModel, value: typeof left) =>
    [
      metric.kind === "pass"
        ? `${value.passed} of ${value.n} rollouts passed`
        : `${value.n} rollouts`,
      model.description,
    ]
      .filter(Boolean)
      .join(" · ");

  return (
    <div className="flex flex-col gap-4">
      <p className="text-base leading-7">
        <strong>{a.name}</strong> {verb} {formatMetric(metric, left.mean)}
        {of}, against {formatMetric(metric, right.mean)} for{" "}
        <strong>{b.name}</strong>.
        {interval
          ? clear
            ? " The difference holds up across cases."
            : " The difference is within case-to-case variation."
          : null}
      </p>
      <div className="grid grid-cols-2 gap-4 border-t pt-4 sm:grid-cols-4">
        <Stat
          label={
            <>
              <Swatch color={MODEL_COLORS[0]} />
              {a.name}
            </>
          }
          value={formatMetric(metric, left.mean)}
          note={note(a, left)}
        />
        <Stat
          label={
            <>
              <Swatch color={MODEL_COLORS[1]} />
              {b.name}
            </>
          }
          value={formatMetric(metric, right.mean)}
          note={note(b, right)}
        />
        <Stat
          label="Difference"
          value={delta === null ? "—" : formatDelta(metric, delta)}
          {...(interval
            ? {
                note: `95% interval ${formatDelta(metric, interval.low)} to ${formatDelta(metric, interval.high)}`,
              }
            : {})}
        />
        <Stat
          label="Evaluated"
          value={`${index.cases.length} cases`}
          note={`${index.eval.rollouts.length} rollouts${incomplete ? ` · ${incomplete} didn’t complete` : ""}`}
        />
      </div>
    </div>
  );
};

export const EvalSummary = (props: EvalProps) => (
  <EvalFigure props={props}>{(ready) => <Summary {...ready} />}</EvalFigure>
);

const Bar = ({
  value,
  color,
  label,
}: {
  value: number;
  color: string;
  label: string;
}) => (
  <div className="flex items-center gap-2">
    <span className="h-2.5 flex-1 overflow-hidden rounded-full bg-muted">
      <span
        className="block h-full rounded-full"
        style={{
          width: `${Math.max(0, Math.min(1, value)) * 100}%`,
          background: color,
        }}
      />
    </span>
    <span className="w-14 text-right text-xs tabular-nums">{label}</span>
  </div>
);

export const EvalBreakdown = (props: EvalProps) => (
  <EvalFigure props={props}>
    {({ index, a, b, metric }) => {
      const scale = metric.kind === "score" ? (metric.max ?? 1) : 1;

      return (
        <div className="flex flex-col gap-3">
          <Legend
            items={[
              [MODEL_COLORS[0], a.name],
              [MODEL_COLORS[1], b.name],
            ]}
          />
          {withAll(index, props.by).map((group) => (
            <GroupRow
              key={group.label}
              label={group.label}
              count={group.ids.length}
            >
              <div className="flex flex-col gap-1">
                {[a, b].map((model, slot) => {
                  const mean = aggregate(
                    index,
                    model.id,
                    metric,
                    group.ids,
                  ).mean;

                  return (
                    <Bar
                      key={model.id}
                      value={(mean ?? 0) / scale}
                      color={MODEL_COLORS[slot]!}
                      label={formatMetric(metric, mean)}
                    />
                  );
                })}
              </div>
            </GroupRow>
          ))}
        </div>
      );
    }}
  </EvalFigure>
);

const VERDICT_COLORS = [
  ["better", MODEL_COLORS[0]],
  ["same", SAME_COLOR],
  ["worse", MODEL_COLORS[1]],
] as const;

export const EvalHeadToHead = (props: EvalProps) => (
  <EvalFigure props={props}>
    {({ index, a, b, metric }) => (
      <div className="flex flex-col gap-3">
        <Legend
          items={[
            [MODEL_COLORS[0], `${a.name} better`],
            [SAME_COLOR, "Same result"],
            [MODEL_COLORS[1], `${b.name} better`],
          ]}
        />
        {withAll(index, props.by).map((group) => {
          const counts: Record<Verdict, number> = {
            better: 0,
            same: 0,
            worse: 0,
          };
          for (const id of group.ids) {
            const { verdict } = verdictOf(index, id, a, b, metric);
            if (verdict) counts[verdict]++;
          }

          return (
            <GroupRow
              key={group.label}
              label={group.label}
              count={group.ids.length}
            >
              <div className="flex flex-col gap-1">
                <div className="flex h-5 overflow-hidden rounded-md bg-muted">
                  {VERDICT_COLORS.map(([verdict, color]) => (
                    <span
                      key={verdict}
                      style={{ flex: counts[verdict], background: color }}
                    />
                  ))}
                </div>
                <span className="text-xs text-muted-foreground">
                  {counts.better} better · {counts.same} same · {counts.worse}{" "}
                  worse
                </span>
              </div>
            </GroupRow>
          );
        })}
      </div>
    )}
  </EvalFigure>
);

const cellColor = (verdict: Verdict | null, delta: number, range: number) => {
  if (verdict === null) return "transparent";
  if (verdict === "same") return SAME_COLOR;

  const slot = verdict === "better" ? 0 : 1;
  return Math.abs(delta) >= range / 2 ? MODEL_COLORS[slot] : LIGHT_COLORS[slot];
};

export const EvalCaseGrid = (props: EvalProps) => {
  const panel = useEvalPanel();

  return (
    <EvalFigure props={props}>
      {({ file, view, index, a, b, metric }) => {
        const range =
          metric.kind === "score" ? (metric.max ?? 1) - (metric.min ?? 0) : 1;
        const grouped = groupCases(index, props.by);
        const untagged = index.cases
          .filter((item) => !props.by || item.tags[props.by] === undefined)
          .map((item) => item.id);
        const groups = [
          ...grouped,
          ...(untagged.length
            ? [{ label: grouped.length ? "None" : "", ids: untagged }]
            : []),
        ];
        const order = groups.flatMap((group) => group.ids);

        return (
          <div className="flex flex-col gap-4">
            <Legend
              items={[
                [MODEL_COLORS[0], `${a.name} much better`],
                [LIGHT_COLORS[0], `${a.name} better`],
                [SAME_COLOR, "Same result"],
                [LIGHT_COLORS[1], `${b.name} better`],
                [MODEL_COLORS[1], `${b.name} much better`],
              ]}
            />
            {groups.map((group) => (
              <div key={group.label} className="flex flex-col gap-2">
                {group.label ? (
                  <span className="text-xs text-muted-foreground">
                    {props.by}: {group.label} · {group.ids.length}
                  </span>
                ) : null}
                <div className="flex flex-wrap gap-1">
                  {group.ids.map((id) => {
                    const item = index.caseById.get(id)!;
                    const { verdict, delta } = verdictOf(
                      index,
                      id,
                      a,
                      b,
                      metric,
                    );

                    return (
                      <button
                        key={id}
                        type="button"
                        aria-label={item.title}
                        title={`${item.title}\n${a.name}: ${rolloutLabel(rolloutsOf(index, id, a.id), metric)}\n${b.name}: ${rolloutLabel(rolloutsOf(index, id, b.id), metric)}`}
                        onClick={() => panel.open(file, id, order, view)}
                        className={cn(
                          "size-5 rounded-[4px] outline-offset-2 hover:outline-2 hover:outline-foreground/40",
                          verdict === null && "border border-dashed",
                        )}
                        style={{ background: cellColor(verdict, delta, range) }}
                      />
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        );
      }}
    </EvalFigure>
  );
};

const STATUS_VERBS = {
  wrong: "got wrong",
  missing: "missed",
  unexpected: "changed without being asked",
} as const;

const reasonFor = (
  index: EvalIndex,
  caseId: string,
  model: EvalModel,
  metric: EvalMetric,
) => {
  const rollouts = rolloutsOf(index, caseId, model.id);
  const failing = rollouts.filter(
    (rollout) => passedOf(rollout, metric) === false,
  );
  const counts = new Map<string, number>();
  for (const rollout of failing) {
    const seen = new Set(
      rollout.checks
        .filter((check) => check.status !== "passed")
        .map((check) => `${check.status}\u0000${check.label}`),
    );
    for (const key of seen) counts.set(key, (counts.get(key) ?? 0) + 1);
  }

  const top = [...counts].sort((left, right) => right[1] - left[1])[0];
  if (!top) return null;

  const [status, label] = top[0].split("\u0000") as [
    keyof typeof STATUS_VERBS,
    string,
  ];
  return `${model.name} ${STATUS_VERBS[status]} ${label.toLowerCase()} in ${top[1]} of ${rollouts.length} rollouts`;
};

export const EvalExamples = (
  props: EvalProps & { where?: "better" | "worse"; limit?: number },
) => {
  const panel = useEvalPanel();

  return (
    <EvalFigure props={props}>
      {({ file, view, index, a, b, metric }) => {
        const where = props.where ?? "better";
        const [winner, loser] = where === "better" ? [a, b] : [b, a];
        const matches = index.cases
          .map((item) => ({ item, ...verdictOf(index, item.id, a, b, metric) }))
          .filter((row) => row.verdict === where)
          .sort((left, right) => Math.abs(right.delta) - Math.abs(left.delta));
        const order = matches.map((row) => row.item.id);

        if (!matches.length)
          return (
            <p className="text-sm text-muted-foreground">
              No cases where {winner.name} did better.
            </p>
          );

        return (
          <ul className="flex list-none flex-col divide-y pl-0!">
            {matches.slice(0, props.limit ?? 5).map(({ item }) => {
              const reason = reasonFor(index, item.id, loser, metric);

              return (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => panel.open(file, item.id, order, view)}
                    className="flex w-full flex-col gap-0.5 py-2.5 text-left"
                  >
                    <span className="font-medium hover:underline">
                      {item.title}
                    </span>
                    <span className="text-xs leading-5 text-muted-foreground">
                      {winner.name}{" "}
                      {rolloutLabel(
                        rolloutsOf(index, item.id, winner.id),
                        metric,
                      )}{" "}
                      · {loser.name}{" "}
                      {rolloutLabel(
                        rolloutsOf(index, item.id, loser.id),
                        metric,
                      )}
                      {reason ? ` · ${reason}` : ""}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        );
      }}
    </EvalFigure>
  );
};

export const ScoreChip = ({
  label,
  rate,
}: {
  label: string;
  rate: number | null;
}) => (
  <span
    className={cn(
      "inline-flex rounded-full px-2 py-0.5 text-xs font-medium tabular-nums",
      rate === null
        ? "bg-muted text-muted-foreground"
        : rate >= 1
          ? "bg-[#e7ecd6] text-[#3d4a14]"
          : rate <= 0
            ? "bg-red-50 text-red-800"
            : "bg-amber-50 text-amber-900",
    )}
  >
    {label}
  </span>
);

export const TagChip = ({ name, value }: { name: string; value: string }) => (
  <span className="inline-flex overflow-hidden rounded-md border text-[11px] leading-5">
    <span className="bg-muted px-1.5 text-muted-foreground">{name}</span>
    <span className="px-1.5">{value}</span>
  </span>
);

const FILTERS = [
  { value: "all", label: "Any result" },
  { value: "differ", label: "Models differ" },
] as const;

const tagId = (key: string, value: string) => `${key}: ${value}`;

const CaseList = ({ file, view, index, a, b, metric }: Ready) => {
  const panel = useEvalPanel();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | "differ">("all");
  const [tags, setTags] = useState<ReadonlySet<string>>(new Set());
  const [limit, setLimit] = useState(25);
  const searchText = useMemo(
    () =>
      new Map(
        index.cases.map((item) => [
          item.id,
          [
            item.title,
            ...item.messages.map((message) => message.content ?? ""),
            ...index.models.flatMap((model) =>
              rolloutsOf(index, item.id, model.id).map(messageText),
            ),
          ]
            .join(" ")
            .toLowerCase(),
        ]),
      ),
    [index],
  );
  const tagValues = useMemo(
    () =>
      index.tagKeys.map((key) => ({
        key,
        values: [
          ...new Set(index.cases.flatMap((item) => item.tags[key] ?? [])),
        ],
      })),
    [index],
  );

  const needle = query.trim().toLowerCase();
  const rows = index.cases.filter(
    (item) =>
      (!needle || searchText.get(item.id)!.includes(needle)) &&
      (filter === "all" ||
        ["better", "worse"].includes(
          verdictOf(index, item.id, a, b, metric).verdict ?? "",
        )) &&
      tagValues.every(({ key, values }) => {
        const chosen = values.filter((value) => tags.has(tagId(key, value)));
        return !chosen.length || chosen.includes(item.tags[key] ?? "");
      }),
  );
  const order = rows.map((item) => item.id);
  const toggle = (tag: string) => {
    const next = new Set(tags);
    if (!next.delete(tag)) next.add(tag);
    setTags(next);
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-48 flex-1">
          <Search
            aria-hidden
            className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search rollouts"
            className="h-8 pl-8"
          />
        </div>
        <SegmentedControl
          value={filter}
          options={FILTERS}
          onValueChange={setFilter}
          label="Result"
        />
      </div>
      <div className="flex flex-wrap gap-1.5">
        {tagValues.flatMap(({ key, values }) =>
          values.map((value) => {
            const id = tagId(key, value);
            const active = tags.has(id);

            return (
              <button
                key={id}
                type="button"
                aria-pressed={active}
                onClick={() => toggle(id)}
                className={cn(
                  "rounded-md border px-2 py-0.5 text-xs",
                  active
                    ? "border-foreground bg-foreground text-background"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {id}
              </button>
            );
          }),
        )}
      </div>
      <table className="w-full table-fixed text-sm">
        <colgroup>
          <col />
          <col className="w-28" />
          <col className="w-28" />
        </colgroup>
        <thead>
          <tr className="border-b text-left text-xs text-muted-foreground">
            <th className="py-2 font-normal">
              {rows.length} of {index.cases.length} cases
            </th>
            <th className="py-2 font-normal">{a.name}</th>
            <th className="py-2 font-normal">{b.name}</th>
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, limit).map((item) => (
            <tr
              key={item.id}
              onClick={() => panel.open(file, item.id, order, view)}
              className="cursor-pointer border-b last:border-0 hover:bg-muted/50"
            >
              <td className="py-2.5 pr-3">
                <div className="flex flex-col gap-1">
                  <span className="font-medium">{item.title}</span>
                  <span className="flex flex-wrap gap-1">
                    {Object.entries(item.tags).map(([key, value]) => (
                      <TagChip key={key} name={key} value={value} />
                    ))}
                  </span>
                </div>
              </td>
              {[a, b].map((model) => (
                <td key={model.id} className="py-2.5">
                  <ScoreChip
                    label={rolloutLabel(
                      rolloutsOf(index, item.id, model.id),
                      metric,
                    )}
                    rate={
                      metric.kind === "pass"
                        ? aggregate(index, model.id, metric, [item.id]).mean
                        : null
                    }
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {rows.length > limit ? (
        <button
          type="button"
          onClick={() => setLimit(limit + 50)}
          className="self-start text-xs text-muted-foreground hover:text-foreground"
        >
          Show {Math.min(50, rows.length - limit)} more
        </button>
      ) : null}
    </div>
  );
};

export const EvalCases = (props: EvalProps) => (
  <EvalFigure props={props}>{(ready) => <CaseList {...ready} />}</EvalFigure>
);
