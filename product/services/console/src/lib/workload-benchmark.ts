import type { WorkloadBenchmark } from "@gradiated/contracts";
import { formatNanoUsd, formatRatio } from "./format";

export const parseBenchmarkUsd = (text: string): number | null => {
  if (!text.trim()) return null;
  if (!/^\d+(\.\d{1,9})?$/.test(text.trim()))
    throw new Error("Enter a USD amount with up to 9 decimal places.");

  const [whole, fraction = ""] = text.trim().split(".");
  const nanos =
    BigInt(whole!) * 1_000_000_000n + BigInt(fraction.padEnd(9, "0"));
  if (nanos > BigInt(Number.MAX_SAFE_INTEGER))
    throw new Error("Cost is too large.");

  return Number(nanos);
};
export const benchmarkUsdInput = (nanos: number | undefined | null) =>
  nanos == null
    ? ""
    : `${BigInt(nanos) / 1_000_000_000n}.${(BigInt(nanos) % 1_000_000_000n).toString().padStart(9, "0")}`;
const advantage = (ratio: number | null, good: string, bad: string) =>
  ratio === null ? "" : ` · ${formatRatio(ratio, good, bad).label}`;

export const benchmarkLabels = (benchmark: WorkloadBenchmark) => ({
  cost: benchmark.cost
    ? `${formatNanoUsd(benchmark.cost.fine_tuned)} / ${benchmark.cost.unit === "task" ? "task" : "1k tokens"}${benchmark.cost.basis === "estimated" ? " est." : ""}${advantage(benchmark.cost.comparison === null || !benchmark.cost.fine_tuned ? null : benchmark.cost.comparison / benchmark.cost.fine_tuned, "cheaper", "more expensive")}`
    : null,
  speed: benchmark.speed
    ? `${benchmark.speed.fine_tuned.toFixed(2)} ${benchmark.speed.unit === "latency_seconds" ? "s" : "tokens/s"}${benchmark.speed.statistic === "median" ? " median" : " mean"}${advantage(benchmark.speed.comparison === null || !benchmark.speed.comparison || !benchmark.speed.fine_tuned ? null : benchmark.speed.unit === "latency_seconds" ? benchmark.speed.comparison / benchmark.speed.fine_tuned : benchmark.speed.fine_tuned / benchmark.speed.comparison, "faster", "slower")}`
    : null,
  quality: benchmark.quality
    ? `${benchmark.quality.fine_tuned.toFixed(1)}% ${benchmark.quality.metric}${benchmark.quality.comparison === null ? "" : ` (vs ${benchmark.quality.comparison.toFixed(1)}%)`}`
    : null,
});
