import type { WorkloadBenchmark } from "@gradiated/contracts";
import { formatNanoUsd, formatRatio, type Ratio } from "./format";

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
const ratio = (value: number | null, good: string, bad: string) =>
  value === null ? null : formatRatio(value, good, bad);
const withRatio = (value: string, advantage: Ratio | null) =>
  advantage ? `${value} · ${advantage.label}` : value;

export const benchmarkRatios = (benchmark: WorkloadBenchmark) => {
  const { cost, speed } = benchmark;

  return {
    cost: cost
      ? ratio(
          cost.comparison === null || !cost.fine_tuned
            ? null
            : cost.comparison / cost.fine_tuned,
          "cheaper",
          "more expensive",
        )
      : null,
    speed: speed
      ? ratio(
          speed.comparison === null || !speed.comparison || !speed.fine_tuned
            ? null
            : speed.unit === "latency_seconds"
              ? speed.comparison / speed.fine_tuned
              : speed.fine_tuned / speed.comparison,
          "faster",
          "slower",
        )
      : null,
  };
};

export const benchmarkValues = (benchmark: WorkloadBenchmark) => ({
  cost: benchmark.cost
    ? `${formatNanoUsd(benchmark.cost.fine_tuned)} / ${benchmark.cost.unit === "task" ? "task" : "1k tokens"}${benchmark.cost.basis === "estimated" ? " est." : ""}`
    : null,
  speed: benchmark.speed
    ? `${benchmark.speed.fine_tuned.toFixed(2)} ${benchmark.speed.unit === "latency_seconds" ? "s" : "tokens/s"}${benchmark.speed.statistic === "median" ? " median" : " mean"}`
    : null,
});

export const benchmarkLabels = (benchmark: WorkloadBenchmark) => {
  const values = benchmarkValues(benchmark);
  const ratios = benchmarkRatios(benchmark);

  return {
    cost: values.cost && withRatio(values.cost, ratios.cost),
    speed: values.speed && withRatio(values.speed, ratios.speed),
    quality: benchmark.quality
      ? `${benchmark.quality.fine_tuned.toFixed(1)}% ${benchmark.quality.metric}${benchmark.quality.comparison === null ? "" : ` (vs ${benchmark.quality.comparison.toFixed(1)}%)`}`
      : null,
  };
};
