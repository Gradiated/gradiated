import { INTERRUPTION_LABEL, PHASE_LABEL, type Tone } from "@/lib/grad/labels";
import type { RunEvent, RunPhase } from "@/lib/grad/types";

export const MAX_CHART_POINTS = 400;

export const MAX_STORED_METRICS = 4_000;

const hasEval = (event: RunEvent) =>
  event.type === "metric" &&
  (typeof event.metric?.evalLoss === "number" ||
    Object.keys(event.metric?.evalMetrics ?? {}).length > 0);

// A long run's stream would otherwise grow without bound in memory. Past the
// cap, every other training-loss point goes; eval points and the newest
// point stay. Charts draw at most MAX_CHART_POINTS anyway.
const thinMetrics = (events: RunEvent[], max: number) => {
  const metrics = events.filter((event) => event.type === "metric").length;
  if (metrics <= max) return events;

  let index = 0;

  return events.filter((event) => {
    if (event.type !== "metric") return true;
    index += 1;

    return index % 2 === 0 || index === metrics || hasEval(event);
  });
};

// `completed` repeats the last stored seq, so it is kept apart from the
// sequence. A resumed run continues the sequence past it, which drops it.
export const mergeRunEvents = (
  current: readonly RunEvent[],
  incoming: readonly RunEvent[],
  maxMetrics = MAX_STORED_METRICS,
): RunEvent[] => {
  const bySeq = new Map<number, RunEvent>();
  let completed: RunEvent | undefined;

  for (const event of [...current, ...incoming]) {
    if (event.type === "completed") completed = event;
    else bySeq.set(event.seq, event);
  }

  const ordered = thinMetrics(
    [...bySeq.values()].sort((a, b) => a.seq - b.seq),
    maxMetrics,
  );
  const last = ordered.at(-1)?.seq ?? 0;

  return completed && completed.seq >= last ? [...ordered, completed] : ordered;
};

export const lastEventSeq = (events: readonly RunEvent[]) =>
  events.reduce(
    (last, event) =>
      event.type === "completed" ? last : Math.max(last, event.seq),
    0,
  );

export const isRunFinished = (events: readonly RunEvent[]) =>
  events.at(-1)?.type === "completed";

export interface LossPoint {
  step: number;
  loss: number;
  evalLoss?: number;
}

export interface EvalPoint {
  step: number;
  values: Record<string, number>;
}

const metricPoints = (events: readonly RunEvent[]) => {
  const byStep = new Map<
    number,
    NonNullable<Extract<RunEvent, { type: "metric" }>["metric"]>
  >();

  // A resumed attempt repeats steps after its checkpoint; the later point wins.
  for (const event of events) {
    if (event.type === "metric" && event.metric)
      byStep.set(event.metric.step, event.metric);
  }

  return [...byStep.values()].sort((a, b) => a.step - b.step);
};

export const downsample = <T extends { step: number }>(
  points: readonly T[],
  keep: (point: T) => boolean,
  maxPoints = MAX_CHART_POINTS,
): T[] => {
  if (points.length <= maxPoints) return [...points];

  const stride = Math.ceil(points.length / maxPoints);

  return points.filter(
    (point, index) =>
      index % stride === 0 || index === points.length - 1 || keep(point),
  );
};

export const lossSeries = (
  events: readonly RunEvent[],
  maxPoints = MAX_CHART_POINTS,
): LossPoint[] =>
  downsample(
    metricPoints(events).map((metric) => ({
      step: metric.step,
      loss: metric.loss,
      ...(typeof metric.evalLoss === "number"
        ? { evalLoss: metric.evalLoss }
        : {}),
    })),
    (point) => point.evalLoss !== undefined,
    maxPoints,
  );

export const evalSeries = (events: readonly RunEvent[]): EvalPoint[] =>
  metricPoints(events).flatMap((metric) => {
    const values = Object.fromEntries(
      Object.entries(metric.evalMetrics ?? {}).filter(
        (entry): entry is [string, number] => typeof entry[1] === "number",
      ),
    );

    return Object.keys(values).length ? [{ step: metric.step, values }] : [];
  });

export const evalMetricNames = (points: readonly EvalPoint[]) => [
  ...new Set(points.flatMap((point) => Object.keys(point.values))),
];

export interface TimelineEntry {
  seq: number;
  at: string;
  attempt: number;
  title: string;
  detail?: string;
  tone: Tone;
}

// Phases that repeat during training are summarised by the step counter, not listed.
const REPEATING_PHASES: ReadonlySet<RunPhase> = new Set([
  "evaluating",
  "checkpointing",
]);

const stepLabel = (step: number) => `step ${step.toLocaleString("en-US")}`;

export const runTimeline = (events: readonly RunEvent[]): TimelineEntry[] => {
  const entries: TimelineEntry[] = [];
  let lastPhase: { attempt: number; phase: RunPhase } | undefined;

  for (const event of events) {
    const base = {
      seq: event.seq,
      at: event.timestamp,
      attempt: event.attempt,
    };

    if (event.type === "phase") {
      if (REPEATING_PHASES.has(event.phase)) continue;
      if (
        lastPhase?.attempt === event.attempt &&
        lastPhase.phase === event.phase
      )
        continue;

      lastPhase = { attempt: event.attempt, phase: event.phase };
      entries.push({
        ...base,
        title: PHASE_LABEL[event.phase],
        ...(event.gpu
          ? { detail: `${event.gpu.name} · ${event.gpu.memoryGb} GB` }
          : event.phase === "training" && event.step > 0
            ? { detail: `From ${stepLabel(event.step)}` }
            : {}),
        tone: event.phase === "waiting_for_compute" ? "warning" : "neutral",
      });
    }

    if (event.type === "attempt") {
      lastPhase = undefined;

      if (event.event === "started") {
        entries.push({
          ...base,
          title: `Attempt ${event.attempt} started`,
          detail:
            event.resumeStep === null
              ? "From the beginning"
              : `Resumed from the checkpoint at ${stepLabel(event.resumeStep)}`,
          tone: "active",
        });
      } else if (event.event === "interrupted") {
        const reason = event.reason
          ? INTERRUPTION_LABEL[event.reason]
          : "Interrupted";
        const at = event.step === null ? "" : ` at ${stepLabel(event.step)}`;

        entries.push({
          ...base,
          title: `${reason}${at}`,
          detail:
            event.resumeStep === null
              ? "The next attempt starts from the beginning."
              : `The next attempt resumes from ${stepLabel(event.resumeStep)}.`,
          tone: "warning",
        });
      } else {
        entries.push({
          ...base,
          title: "No attempts left",
          detail: `Stopped after ${event.maxAttempts} attempts without a result.`,
          tone: "danger",
        });
      }
    }

    if (event.type === "warning") {
      entries.push({
        ...base,
        title: "Warning",
        detail: event.message,
        tone: "warning",
      });
    }

    if (event.type === "completed") {
      entries.push({
        ...base,
        title:
          event.status === "completed"
            ? "Run completed"
            : event.status === "failed"
              ? "Run failed"
              : event.status === "cancelled"
                ? "Run cancelled"
                : "Run stopped",
        tone:
          event.status === "completed"
            ? "success"
            : event.status === "failed"
              ? "danger"
              : "neutral",
      });
    }
  }

  return entries;
};

export const PHASE_STEPS = [
  { key: "queued", label: "Queued", phases: ["queued", "waiting_for_compute"] },
  { key: "starting", label: "Starting", phases: ["starting", "loading_model"] },
  {
    key: "training",
    label: "Training",
    phases: ["training", "evaluating", "checkpointing"],
  },
  { key: "uploading", label: "Uploading", phases: ["uploading", "completing"] },
] as const satisfies readonly {
  key: string;
  label: string;
  phases: readonly RunPhase[];
}[];

export const phaseStepIndex = (phase: RunPhase | null) =>
  phase === null
    ? 0
    : PHASE_STEPS.findIndex((step) =>
        (step.phases as readonly RunPhase[]).includes(phase),
      );
