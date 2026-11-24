import {
  EvalSchema,
  type Eval,
  type EvalCase,
  type EvalMetric,
  type EvalModel,
  type EvalRollout,
} from "@gradiated/contracts";

export type EvalIndex = {
  eval: Eval;
  metric: EvalMetric;
  models: EvalModel[];
  cases: EvalCase[];
  caseById: ReadonlyMap<string, EvalCase>;
  rollouts: ReadonlyMap<string, ReadonlyMap<string, EvalRollout[]>>;
  tagKeys: string[];
};

export type Verdict = "better" | "same" | "worse";

export const parseEval = (text: string): EvalIndex => {
  const result = EvalSchema.safeParse(JSON.parse(text));
  if (!result.success)
    throw new Error(
      `Not a valid eval file: ${result.error.issues[0]?.message ?? "unknown problem"} at ${result.error.issues[0]?.path.join(".") ?? ""}`,
    );

  const data = result.data;
  const rollouts = new Map<string, Map<string, EvalRollout[]>>();
  for (const item of data.cases)
    rollouts.set(item.id, new Map(data.models.map((model) => [model.id, []])));
  for (const rollout of data.rollouts)
    rollouts.get(rollout.case_id)?.get(rollout.model_id)?.push(rollout);

  const tagKeys = [
    ...new Set(data.cases.flatMap((item) => Object.keys(item.tags))),
  ];

  return {
    eval: data,
    metric: data.metrics.find((metric) => metric.id === data.primary_metric)!,
    models: data.models,
    cases: data.cases,
    caseById: new Map(data.cases.map((item) => [item.id, item])),
    rollouts,
    tagKeys,
  };
};

export const pickModels = (index: EvalIndex, ids?: unknown) => {
  const wanted = Array.isArray(ids) ? [...new Set(ids.map(String))] : [];
  const chosen = wanted
    .map((id) => index.models.find((model) => model.id === id))
    .filter((model): model is EvalModel => Boolean(model));

  return chosen.length >= 2 ? chosen.slice(0, 2) : index.models.slice(0, 2);
};

export const pickMetric = (index: EvalIndex, id?: unknown) =>
  index.eval.metrics.find((metric) => metric.id === id) ?? index.metric;

export const rolloutsOf = (index: EvalIndex, caseId: string, modelId: string) =>
  index.rollouts.get(caseId)?.get(modelId) ?? [];

export const scoreOf = (rollout: EvalRollout, metric: EvalMetric) => {
  if (rollout.status !== "completed") return null;

  const value = rollout.scores[metric.id];
  if (value === undefined || value === null) return null;

  return typeof value === "boolean" ? (value ? 1 : 0) : value;
};

export const passedOf = (rollout: EvalRollout, metric: EvalMetric) => {
  const value = scoreOf(rollout, metric);
  if (value === null) return null;
  if (metric.kind === "pass") return value === 1;
  if (metric.pass_at === undefined) return null;

  return metric.higher_is_better
    ? value >= metric.pass_at
    : value <= metric.pass_at;
};

export type Aggregate = {
  mean: number | null;
  n: number;
  passed: number;
  incomplete: number;
};

export const aggregate = (
  index: EvalIndex,
  modelId: string,
  metric: EvalMetric,
  caseIds?: Iterable<string>,
): Aggregate => {
  let sum = 0;
  let n = 0;
  let passed = 0;
  let incomplete = 0;

  for (const caseId of caseIds ?? index.caseById.keys())
    for (const rollout of rolloutsOf(index, caseId, modelId)) {
      const value = scoreOf(rollout, metric);
      if (value === null) {
        if (rollout.status !== "completed") incomplete++;
        continue;
      }

      sum += value;
      n++;
      if (passedOf(rollout, metric)) passed++;
    }

  return { mean: n ? sum / n : null, n, passed, incomplete };
};

export const caseMean = (
  index: EvalIndex,
  caseId: string,
  modelId: string,
  metric: EvalMetric,
) => aggregate(index, modelId, metric, [caseId]).mean;

export const verdictOf = (
  index: EvalIndex,
  caseId: string,
  a: EvalModel,
  b: EvalModel,
  metric: EvalMetric,
): { verdict: Verdict | null; delta: number } => {
  const left = caseMean(index, caseId, a.id, metric);
  const right = caseMean(index, caseId, b.id, metric);
  if (left === null || right === null) return { verdict: null, delta: 0 };

  const delta = (left - right) * (metric.higher_is_better ? 1 : -1);
  const margin = metric.tie_margin ?? (metric.kind === "pass" ? 1e-9 : 0);
  if (Math.abs(delta) <= margin) return { verdict: "same", delta };

  return { verdict: delta > 0 ? "better" : "worse", delta };
};

export const groupCases = (index: EvalIndex, by?: unknown) => {
  const key = typeof by === "string" && index.tagKeys.includes(by) ? by : null;
  if (!key) return [];

  const groups = new Map<string, string[]>();
  for (const item of index.cases) {
    const value = item.tags[key];
    if (value === undefined) continue;
    groups.set(value, [...(groups.get(value) ?? []), item.id]);
  }

  return [...groups.entries()]
    .sort((left, right) => right[1].length - left[1].length)
    .map(([label, ids]) => ({ label, ids }));
};

export const tagGroups = (index: EvalIndex, by?: unknown) => {
  const groups = groupCases(index, by);
  const untagged = index.cases
    .filter((item) => item.tags[String(by)] === undefined)
    .map((item) => item.id);

  return groups.length && untagged.length
    ? [...groups, { label: `No ${String(by)}`, ids: untagged }]
    : groups;
};

export const isRate = (metric: EvalMetric) =>
  metric.kind === "pass" ||
  (metric.kind === "score" && metric.min === 0 && metric.max === 1);

export const formatMetric = (metric: EvalMetric, value: number | null) => {
  if (value === null) return "—";
  if (isRate(metric))
    return `${(value * 100).toLocaleString(undefined, { maximumFractionDigits: 1, minimumFractionDigits: 1 })}%`;
  if (metric.unit === "usd")
    return value.toLocaleString(undefined, {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: value < 1 ? 4 : 2,
    });

  const number = value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return metric.unit ? `${number} ${metric.unit}` : number;
};

export const formatDelta = (metric: EvalMetric, delta: number) => {
  const sign = delta > 0 ? "+" : delta < 0 ? "−" : "";
  const size = Math.abs(delta);
  if (isRate(metric))
    return `${sign}${(size * 100).toLocaleString(undefined, { maximumFractionDigits: 1, minimumFractionDigits: 1 })} pts`;

  return `${sign}${size.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
};

export const rolloutLabel = (rollouts: EvalRollout[], metric: EvalMetric) => {
  const values = rollouts.map((rollout) => scoreOf(rollout, metric));
  const done = values.filter((value): value is number => value !== null);
  if (!done.length) return "—";
  if (metric.kind === "pass")
    return `${done.filter((value) => value === 1).length}/${done.length}`;

  return formatMetric(
    metric,
    done.reduce((sum, value) => sum + value, 0) / done.length,
  );
};

export const checkCounts = (rollout: EvalRollout) => {
  const counts = { passed: 0, wrong: 0, missing: 0, unexpected: 0 };
  for (const check of rollout.checks) counts[check.status]++;

  return counts;
};

export const messageText = (rollout: EvalRollout) =>
  rollout.messages
    .map((message) =>
      [
        message.content ?? "",
        ...(message.tool_calls ?? []).map(
          (call) => `${call.function.name} ${call.function.arguments}`,
        ),
      ].join(" "),
    )
    .join(" ");

// Mulberry32: a seeded generator keeps the interval stable between renders.
const seeded = (seed: number) => () => {
  seed = (seed + 0x6d2b79f5) | 0;
  let value = Math.imul(seed ^ (seed >>> 15), 1 | seed);
  value = (value + Math.imul(value ^ (value >>> 7), 61 | value)) ^ value;
  return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
};

// Resamples interval_group_by groups (untagged cases alone): rollouts of one
// case or project aren't independent. Only groups scored for both models count.
export const differenceInterval = (
  index: EvalIndex,
  a: EvalModel,
  b: EvalModel,
  metric: EvalMetric,
) => {
  const key = index.eval.interval_group_by;
  const groups = [
    ...(key ? groupCases(index, key).map((group) => group.ids) : []),
    ...index.cases
      .filter((item) => !key || item.tags[key] === undefined)
      .map((item) => [item.id]),
  ];
  const totals = groups
    .map((ids) => ({
      a: aggregate(index, a.id, metric, ids),
      b: aggregate(index, b.id, metric, ids),
    }))
    .filter((total) => total.a.n && total.b.n);
  if (totals.length < 2) return null;

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
