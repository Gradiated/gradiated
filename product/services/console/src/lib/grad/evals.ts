import type { Tone } from "@/lib/grad/labels";
import type { EvalModelSummary } from "@/lib/grad/types";

const signed = (value: number) =>
  `${value < 0 ? "−" : ""}${Math.abs(value).toFixed(3)}`;

export const formatInterval = (low: number, high: number) =>
  `${signed(low)} to ${signed(high)}`;

export const formatDelta = (delta: number) =>
  `${delta >= 0 ? "+" : "−"}${Math.abs(delta).toFixed(3)}`;

// The difference only counts when its 95% interval excludes zero.
export const deltaTone = (
  vsBaseline: NonNullable<EvalModelSummary["vsBaseline"]>,
): Tone => {
  if (vsBaseline.ciLow > 0) return "success";
  if (vsBaseline.ciHigh < 0) return "danger";

  return "neutral";
};

export const passAtK = (summary: EvalModelSummary) =>
  Object.entries(summary.passAtK)
    .sort(([a], [b]) => Number(a) - Number(b))
    .map(([k, value]) => ({ k: Number(k), value }));

export const bestModel = (summaries: readonly EvalModelSummary[]) =>
  summaries.reduce<EvalModelSummary | undefined>(
    (best, summary) =>
      best === undefined || summary.overall > best.overall ? summary : best,
    undefined,
  );
