import type { EvalMetric, EvalModel } from "@gradiated/contracts";
import { Search } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";

import { MultiCombobox } from "@/components/multi-combobox";
import { SegmentedControl } from "@/components/segmented-control";
import { Input } from "@/components/ui/input";
import {
  aggregate,
  differenceInterval,
  formatDelta,
  formatMetric,
  isRate,
  messageText,
  pickMetric,
  pickModels,
  rolloutLabel,
  rolloutsOf,
  tagGroups,
  verdictOf,
  type EvalIndex,
  type Verdict,
} from "@/lib/eval-data";
import { cn } from "@/lib/utils";
import { DatasetState } from "./report-blocks";
import { useEvalDataset, useEvalPanel, type EvalView } from "./eval-context";
import {
  Legend,
  MODEL_COLORS,
  ModelMark,
  Panel,
  SAME_COLOR,
  ScoreChip,
  Swatch,
} from "./eval-ui";

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

const tasks = (count: number) => `${count} task${count === 1 ? "" : "s"}`;
const runs = (count: number) => `${count} run${count === 1 ? "" : "s"}`;

const EvalPanel = ({
  props,
  children,
}: {
  props: EvalProps;
  children: (ready: Ready) => ReactNode;
}) => {
  const dataset = useEvalDataset(props.eval);
  if (dataset.status !== "ready")
    return (
      <Panel title={props.title} subtitle={props.caption}>
        <DatasetState dataset={dataset} name={props.eval} />
      </Panel>
    );

  const [a, b] = pickModels(dataset.index, props.models);
  const metric = pickMetric(dataset.index, props.metric);

  return (
    <Panel title={props.title} subtitle={props.caption}>
      {children({
        file: props.eval,
        index: dataset.index,
        a: a!,
        b: b!,
        metric,
        view: { models: [a!.id, b!.id], metric: metric.id },
      })}
    </Panel>
  );
};

// One row per group; the whole set only when the block is not grouped.
const rowGroups = (index: EvalIndex, by?: string) => {
  const groups = tagGroups(index, by);
  return groups.length
    ? groups
    : [{ label: "All tasks", ids: index.cases.map((item) => item.id) }];
};

const GroupRow = ({
  label,
  count,
  children,
}: {
  label: string;
  count: number;
  children: ReactNode;
}) => (
  <div className="grid grid-cols-[minmax(7rem,11rem)_minmax(0,1fr)] items-center gap-4">
    <span className="flex flex-col text-sm leading-5">
      {label}
      <span className="text-xs leading-4 text-muted-foreground">
        {tasks(count)}
      </span>
    </span>
    {children}
  </div>
);

const direction = (metric: EvalMetric) => (metric.higher_is_better ? 1 : -1);

const Headline = ({ index, a, b, metric, by }: Ready & { by?: string }) => {
  const left = aggregate(index, a.id, metric).mean;
  const right = aggregate(index, b.id, metric).mean;
  const interval = differenceInterval(index, a, b, metric);
  if (left === null || right === null)
    return (
      <p className="text-[19px] leading-8 font-normal tracking-[-0.01em]">
        There are not enough scored runs to compare{" "}
        <strong className="font-semibold">{a.name}</strong> with{" "}
        <strong className="font-semibold">{b.name}</strong>.
      </p>
    );
  const delta = (left - right) * direction(metric);
  const clear = interval && (interval.low > 0 || interval.high < 0);
  const margin = isRate(metric) ? 0.03 : (metric.tie_margin ?? 0);
  const verb = clear
    ? delta > 0
      ? "outperforms"
      : "trails"
    : Math.abs(delta) <= margin
      ? "performs on par with"
      : null;
  const what = metric.kind === "pass" ? " of runs pass" : "";
  const groups = tagGroups(index, by)
    .filter((group) => group.ids.length >= 5)
    .map((group) => {
      const groupLeft = aggregate(index, a.id, metric, group.ids).mean;
      const groupRight = aggregate(index, b.id, metric, group.ids).mean;
      return {
        label: group.label,
        delta:
          groupLeft === null || groupRight === null
            ? 0
            : (groupLeft - groupRight) * direction(metric),
      };
    });
  const ahead = [...groups].sort((x, y) => y.delta - x.delta)[0];
  const behind = [...groups].sort((x, y) => x.delta - y.delta)[0];
  const parts = [
    ahead && ahead.delta > margin
      ? `ahead on ${ahead.label.toLowerCase()} tasks (${formatDelta(metric, ahead.delta)})`
      : null,
    behind && behind.delta < -margin
      ? `behind on ${behind.label.toLowerCase()} tasks (${formatDelta(metric, behind.delta)})`
      : null,
  ].filter(Boolean);

  const scores = `${formatMetric(metric, left)}${what}, against ${formatMetric(metric, right)}`;

  return (
    <p className="text-[19px] leading-8 font-normal tracking-[-0.01em]">
      <strong className="font-semibold">{a.name}</strong>{" "}
      {verb ? (
        <>
          {verb} <strong className="font-semibold">{b.name}</strong>: {scores}.
        </>
      ) : (
        <>
          {metric.kind === "pass" ? "passes" : "averages"}{" "}
          {formatMetric(metric, left)}
          {metric.kind === "pass" ? " of runs" : ""}, against{" "}
          {formatMetric(metric, right)} for{" "}
          <strong className="font-semibold">{b.name}</strong>. The gap is not
          conclusive on {tasks(index.cases.length)}.
        </>
      )}
      {verb && parts.length ? ` It is ${parts.join(" and ")}.` : ""}
    </p>
  );
};

const Stat = ({
  label,
  value,
  note,
}: {
  label: ReactNode;
  value: string;
  note?: string | undefined;
}) => (
  <div className="flex min-w-0 flex-col gap-1">
    <span className="flex items-center gap-1.5 text-[12.5px] text-muted-foreground">
      {label}
    </span>
    <span className="text-[28px] leading-9 font-semibold tracking-[-0.02em] tabular-nums">
      {value}
    </span>
    {note ? (
      <span className="text-xs leading-5 text-muted-foreground">{note}</span>
    ) : null}
  </div>
);

const Summary = (ready: Ready & { by?: string }) => {
  const { index, a, b, metric } = ready;
  const left = aggregate(index, a.id, metric);
  const right = aggregate(index, b.id, metric);
  const delta =
    left.mean !== null && right.mean !== null
      ? (left.mean - right.mean) * direction(metric)
      : null;
  const total = index.eval.rollouts.filter(
    (rollout) => rollout.model_id === a.id || rollout.model_id === b.id,
  ).length;
  const modelNote = (value: typeof left) =>
    metric.kind === "pass"
      ? `${value.passed} of ${value.n} runs passed`
      : runs(value.n);

  return (
    <div className="flex flex-col gap-5">
      <Headline {...ready} />
      <div className="grid grid-cols-2 gap-6 border-t pt-5 sm:grid-cols-4">
        {[a, b].map((model, slot) => (
          <Stat
            key={model.id}
            label={
              <>
                <Swatch color={MODEL_COLORS[slot]!} />
                {model.name}
              </>
            }
            value={formatMetric(metric, slot ? right.mean : left.mean)}
            note={modelNote(slot ? right : left)}
          />
        ))}
        <Stat
          label="Difference"
          value={delta === null ? "—" : formatDelta(metric, delta)}
        />
        <Stat
          label="Evaluated"
          value={tasks(index.cases.length)}
          note={runs(total)}
        />
      </div>
    </div>
  );
};

export const EvalSummary = (props: EvalProps) => (
  <EvalPanel props={props}>
    {(ready) => <Summary {...ready} {...(props.by ? { by: props.by } : {})} />}
  </EvalPanel>
);

export const EvalBreakdown = (props: EvalProps) => (
  <EvalPanel props={props}>
    {({ index, a, b, metric }) => {
      const rows = rowGroups(index, props.by).map((group) => ({
        group,
        means: [a, b].map(
          (model) => aggregate(index, model.id, metric, group.ids).mean,
        ),
      }));
      const scale = isRate(metric)
        ? 1
        : (metric.max ??
          Math.max(
            ...rows.flatMap((row) => row.means.map((mean) => mean ?? 0)),
          ));

      return (
        <div className="flex flex-col gap-4">
          <Legend
            items={[
              [MODEL_COLORS[0], a.name],
              [MODEL_COLORS[1], b.name],
            ]}
          />
          {rows.map(({ group, means }) => (
            <GroupRow
              key={group.label}
              label={group.label}
              count={group.ids.length}
            >
              <div className="flex flex-col gap-1.5">
                {means.map((mean, slot) => (
                  <div key={slot} className="flex items-center gap-2">
                    <span
                      className="h-2 rounded-[2px]"
                      style={{
                        width: `${Math.min(1, scale ? (mean ?? 0) / scale : 0) * 85}%`,
                        background: MODEL_COLORS[slot],
                      }}
                    />
                    <span className="text-xs tabular-nums">
                      {formatMetric(metric, mean)}
                    </span>
                  </div>
                ))}
              </div>
            </GroupRow>
          ))}
        </div>
      );
    }}
  </EvalPanel>
);

export const EvalHeadToHead = (props: EvalProps) => (
  <EvalPanel props={props}>
    {({ index, a, b, metric }) => (
      <div className="flex flex-col gap-4">
        <Legend
          items={[
            [MODEL_COLORS[0], a.name],
            [MODEL_COLORS[1], b.name],
          ]}
        />
        {rowGroups(index, props.by).map((group) => {
          const counts: Record<Verdict | "none", number> = {
            better: 0,
            same: 0,
            worse: 0,
            none: 0,
          };
          for (const id of group.ids)
            counts[verdictOf(index, id, a, b, metric).verdict ?? "none"]++;

          return (
            <GroupRow
              key={group.label}
              label={group.label}
              count={group.ids.length}
            >
              <div className="flex flex-col">
                <div className="my-0.5 flex h-4 gap-px overflow-hidden rounded-[4px]">
                  {(
                    [
                      ["better", MODEL_COLORS[0]],
                      ["same", SAME_COLOR],
                      ["worse", MODEL_COLORS[1]],
                      ["none", "transparent"],
                    ] as const
                  ).map(([key, color]) =>
                    counts[key] ? (
                      <span
                        key={key}
                        style={{ flex: counts[key], background: color }}
                      />
                    ) : null,
                  )}
                </div>
                <span className="text-xs leading-4 text-muted-foreground tabular-nums">
                  {counts.better} better · {counts.same} same · {counts.worse}{" "}
                  worse
                  {counts.none ? ` · ${counts.none} without a result` : ""}
                </span>
              </div>
            </GroupRow>
          );
        })}
      </div>
    )}
  </EvalPanel>
);

const cellColor = (
  index: EvalIndex,
  id: string,
  a: EvalModel,
  b: EvalModel,
  metric: EvalMetric,
) => {
  const { verdict } = verdictOf(index, id, a, b, metric);
  if (verdict === null) return "transparent";
  if (verdict === "same") return SAME_COLOR;

  return MODEL_COLORS[verdict === "better" ? 0 : 1];
};

export const EvalCaseGrid = (props: EvalProps) => {
  const panel = useEvalPanel();

  return (
    <EvalPanel props={props}>
      {({ file, view, index, a, b, metric }) => {
        const grouped = tagGroups(index, props.by);
        const groups = grouped.length
          ? grouped
          : [{ label: "", ids: index.cases.map((item) => item.id) }];
        const order = groups.flatMap((group) => group.ids);

        return (
          <div className="flex flex-col gap-4">
            <Legend
              items={[
                [MODEL_COLORS[0], a.name],
                [MODEL_COLORS[1], b.name],
              ]}
            />
            {groups.map((group) => (
              <div key={group.label} className="flex flex-col gap-2">
                {group.label ? (
                  <span className="text-xs text-muted-foreground">
                    {props.by}: {group.label} · {group.ids.length}
                  </span>
                ) : null}
                <div className="flex flex-wrap gap-[5px]">
                  {group.ids.map((id) => {
                    const item = index.caseById.get(id)!;
                    const color = cellColor(index, id, a, b, metric);

                    return (
                      <button
                        key={id}
                        type="button"
                        aria-label={item.title}
                        title={`${item.title}\n${a.name}: ${rolloutLabel(rolloutsOf(index, id, a.id), metric)}\n${b.name}: ${rolloutLabel(rolloutsOf(index, id, b.id), metric)}`}
                        onClick={() => panel.open(file, id, order, view)}
                        className={cn(
                          "size-[22px] rounded-[4px] transition-transform hover:scale-110 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none",
                          color === "transparent" && "border border-dashed",
                        )}
                        style={{ background: color }}
                      />
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        );
      }}
    </EvalPanel>
  );
};

export const EvalExamples = (
  props: EvalProps & { where?: "better" | "worse"; limit?: number },
) => {
  const panel = useEvalPanel();

  return (
    <EvalPanel props={props}>
      {({ file, view, index, a, b, metric }) => {
        const where = props.where ?? "better";
        const winner = where === "better" ? a : b;
        const matches = index.cases
          .map((item) => ({ item, ...verdictOf(index, item.id, a, b, metric) }))
          .filter((row) => row.verdict === where)
          .sort((x, y) => Math.abs(y.delta) - Math.abs(x.delta));
        const order = matches.map((row) => row.item.id);

        if (!matches.length)
          return (
            <p className="text-sm text-muted-foreground">
              No tasks where {winner.name} did better.
            </p>
          );

        return (
          <div className="-mt-1 flex flex-col divide-y">
            {matches.slice(0, props.limit ?? 5).map(({ item }) => (
              <button
                key={item.id}
                type="button"
                onClick={() => panel.open(file, item.id, order, view)}
                className="group flex flex-col gap-1.5 py-3 text-left"
              >
                <span className="text-sm leading-5 font-medium group-hover:underline">
                  {item.title}
                </span>
                <span className="flex flex-wrap items-center gap-1.5">
                  {[a, b].map((model) => (
                    <ScoreChip
                      key={model.id}
                      model={model}
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
                  ))}
                </span>
              </button>
            ))}
          </div>
        );
      }}
    </EvalPanel>
  );
};

const FILTERS = [
  { value: "all", label: "Any result" },
  { value: "differ", label: "Models differ" },
] as const;

const CaseList = ({ file, view, index, a, b, metric }: Ready) => {
  const panel = useEvalPanel();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<"all" | "differ">("all");
  const [tags, setTags] = useState<Record<string, ReadonlySet<string>>>({});
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
      index.tagKeys.map((key) => {
        const counts = new Map<string, number>();
        for (const item of index.cases) {
          const value = item.tags[key];
          if (value !== undefined)
            counts.set(value, (counts.get(value) ?? 0) + 1);
        }
        return { key, values: [...counts] };
      }),
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
      tagValues.every(({ key }) => {
        const chosen = tags[key];
        return !chosen?.size || chosen.has(item.tags[key] ?? "");
      }),
  );
  const order = rows.map((item) => item.id);

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
            placeholder="Search tasks"
            className="h-8 bg-card pl-8"
          />
        </div>
        <SegmentedControl
          value={filter}
          options={FILTERS}
          onValueChange={setFilter}
          label="Result"
        />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {tagValues.map(({ key, values }) => (
          <MultiCombobox
            key={key}
            label={key}
            options={values.map(([value, count]) => ({
              value,
              label: value,
              count,
            }))}
            value={tags[key] ?? new Set()}
            onValueChange={(next) => setTags({ ...tags, [key]: next })}
          />
        ))}
      </div>
      <div className="overflow-hidden rounded-xl border bg-card">
        <table className="w-full table-fixed text-sm">
          <colgroup>
            <col />
            <col className="w-40" />
            <col className="w-40" />
          </colgroup>
          <thead>
            <tr className="border-b text-left text-xs text-muted-foreground">
              <th className="px-4 py-2.5 font-normal">Task</th>
              {[a, b].map((model) => (
                <th key={model.id} className="px-4 py-2.5 font-normal">
                  <span className="inline-flex items-center gap-1.5">
                    <ModelMark model={model} />
                    {model.name}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, limit).map((item) => {
              const open = () => panel.open(file, item.id, order, view);

              return (
                <tr
                  key={item.id}
                  tabIndex={0}
                  aria-label={`Open ${item.title}`}
                  onClick={open}
                  onKeyDown={(event) => {
                    if (event.key !== "Enter" && event.key !== " ") return;

                    event.preventDefault();
                    open();
                  }}
                  className="cursor-pointer border-b align-top outline-none last:border-0 hover:bg-muted/40 focus-visible:bg-muted/40"
                >
                  <td className="px-4 py-3 leading-5 font-medium">
                    {item.title}
                  </td>
                  {[a, b].map((model) => (
                    <td key={model.id} className="px-4 py-3">
                      <ScoreChip
                        model={model}
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
              );
            })}
          </tbody>
        </table>
      </div>
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

export const EvalCases = (props: EvalProps) => {
  const dataset = useEvalDataset(props.eval);
  if (dataset.status !== "ready")
    return <DatasetState dataset={dataset} name={props.eval} />;

  const [a, b] = pickModels(dataset.index, props.models);
  const metric = pickMetric(dataset.index, props.metric);

  const list = (
    <CaseList
      file={props.eval}
      index={dataset.index}
      a={a!}
      b={b!}
      metric={metric}
      view={{ models: [a!.id, b!.id], metric: metric.id }}
    />
  );

  return props.title || props.caption ? (
    <div className="flex flex-col gap-3">
      <header className="flex flex-col gap-1">
        {props.title ? (
          <h3 className="text-[15px] leading-5 font-semibold">{props.title}</h3>
        ) : null}
        {props.caption ? (
          <p className="text-[13px] leading-5 text-muted-foreground">
            {props.caption}
          </p>
        ) : null}
      </header>
      {list}
    </div>
  ) : (
    list
  );
};
