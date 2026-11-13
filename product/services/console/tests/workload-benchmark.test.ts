import { describe, expect, it } from "vitest";
import { WorkloadBenchmarkSchema } from "@gradiated/contracts";
import {
  benchmarkLabels,
  benchmarkRatios,
  benchmarkValues,
  benchmarkUsdInput,
  parseBenchmarkUsd,
} from "@/lib/workload-benchmark";

const benchmark = {
  schema_version: 1,
  comparison_model_id: "anthropic/claude-sonnet-5-5",
  workload: "Play next-turn decisions",
  notes: "",
  cost: {
    unit: "task",
    fine_tuned: 266433,
    comparison: null,
    basis: "estimated",
  },
  speed: {
    unit: "latency_seconds",
    fine_tuned: 2.5806,
    comparison: null,
    statistic: "median",
  },
  quality: {
    metric: "acceptance",
    fine_tuned: 76.5625,
    comparison: null,
    sample_size: 64,
  },
};

describe("manual workload benchmarks", () => {
  it("accepts external results without inventing comparison measurements", () => {
    const parsed = WorkloadBenchmarkSchema.parse(benchmark);
    expect(parsed.cost?.comparison).toBeNull();
    expect(benchmarkLabels(parsed)).toEqual({
      cost: "$0.000266 / task est.",
      speed: "2.58 s median",
      quality: "76.6% acceptance",
    });
  });
  it("supports tokens/second and cost per 1k tokens", () => {
    const parsed = WorkloadBenchmarkSchema.parse({
      ...benchmark,
      cost: { ...benchmark.cost, unit: "1k_tokens" },
      speed: { ...benchmark.speed, unit: "output_tokens_per_second" },
    });
    expect(benchmarkLabels(parsed).cost).toContain("1k tokens");
    expect(benchmarkLabels(parsed).speed).toContain("tokens/s");
  });
  it("splits the value from the comparison for the training table", () => {
    const parsed = WorkloadBenchmarkSchema.parse({
      ...benchmark,
      cost: {
        ...benchmark.cost,
        fine_tuned: 3_320_000,
        comparison: 60_000_000,
      },
      speed: {
        ...benchmark.speed,
        statistic: "mean",
        fine_tuned: 11.8,
        comparison: 14.6,
      },
    });
    expect(benchmarkValues(parsed)).toEqual({
      cost: "$0.00332 / task est.",
      speed: "11.80 s mean",
    });
    expect(benchmarkRatios(parsed)).toEqual({
      cost: { tone: "good", label: "18.1× cheaper" },
      speed: { tone: "good", label: "23.7% faster" },
    });
    expect(benchmarkLabels(parsed).speed).toBe("11.80 s mean · 23.7% faster");
  });
  it("accepts paired run outcomes and rejects an empty set", () => {
    const quality = { ...benchmark.quality, fine_tuned: 100, comparison: 75 };
    expect(
      WorkloadBenchmarkSchema.parse({
        ...benchmark,
        quality: { ...quality, outcome: { better: 18, same: 54, worse: 0 } },
      }).quality?.outcome,
    ).toEqual({ better: 18, same: 54, worse: 0 });
    expect(
      WorkloadBenchmarkSchema.safeParse({
        ...benchmark,
        quality: { ...quality, outcome: { better: 0, same: 0, worse: 0 } },
      }).success,
    ).toBe(false);
  });
  it("retains missing metrics as missing", () => {
    expect(
      benchmarkLabels(
        WorkloadBenchmarkSchema.parse({
          ...benchmark,
          cost: null,
          speed: null,
          quality: null,
        }),
      ),
    ).toEqual({ cost: null, speed: null, quality: null });
  });
  it.each([
    { schema_version: 2 },
    { workload: " " },
    { cost: { ...benchmark.cost, fine_tuned: -1 } },
    { cost: { ...benchmark.cost, fine_tuned: Number.MAX_SAFE_INTEGER + 1 } },
    { speed: { ...benchmark.speed, fine_tuned: 0 } },
    { quality: { ...benchmark.quality, fine_tuned: 101 } },
    { quality: { ...benchmark.quality, sample_size: 0 } },
    { arbitrary: "unversioned field" },
  ])("rejects invalid benchmark values %j", (patch) => {
    expect(
      WorkloadBenchmarkSchema.safeParse({ ...benchmark, ...patch }).success,
    ).toBe(false);
  });
  it("round trips tiny USD values exactly", () => {
    for (const amount of [0, 1, 266433, 999999999, Number.MAX_SAFE_INTEGER]) {
      expect(parseBenchmarkUsd(benchmarkUsdInput(amount))).toBe(amount);
    }
    expect(parseBenchmarkUsd("0.000266433")).toBe(266433);
    expect(parseBenchmarkUsd("")).toBeNull();
  });
  it.each(["-1", "1e-6", "0.0000000001", "NaN", "9007199.254740992"])(
    "rejects ambiguous or overflowing currency %s",
    (value) => {
      expect(() => parseBenchmarkUsd(value)).toThrow();
    },
  );
});
