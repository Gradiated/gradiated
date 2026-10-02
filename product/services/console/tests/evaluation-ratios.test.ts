import { describe, expect, it } from "vitest";

import {
  costAdvantage,
  costPer1kRequests,
  outputSpeed,
  speedAdvantage,
} from "@/components/fine-tuning/evaluation-ratios";
import type { EvaluationSummary } from "@/store/fine-tuning-types";

const summary = (
  cost: { fine_tuned: number; comparison: number },
  speed: { fine_tuned: number; comparison: number },
): EvaluationSummary => ({
  holdout_groups: 10,
  holdout_examples: 30,
  comparison_model_id: "gpt-4o",
  judge_model_id: "openai/gpt-5",
  vs_comparison: {
    comparator_model_id: "gpt-4o",
    win: 0.4,
    tie: 0.3,
    loss: 0.25,
    unresolved: 0.05,
  },
  cost_per_request_nano_usd: cost,
  output_tokens_per_second: speed,
  error_rate: 0.01,
});

describe("costAdvantage", () => {
  it("reads a cheaper fine-tuned model as good", () => {
    expect(
      costAdvantage(
        summary(
          { fine_tuned: 100, comparison: 520 },
          { fine_tuned: 1, comparison: 1 },
        ),
      ),
    ).toEqual({ tone: "good", label: "5.2× cheaper" });
  });

  it("shows n/a when the fine-tuned cost is zero", () => {
    expect(
      costAdvantage(
        summary(
          { fine_tuned: 0, comparison: 520 },
          { fine_tuned: 1, comparison: 1 },
        ),
      ),
    ).toEqual({ tone: "neutral", label: "n/a" });
  });
});

describe("speedAdvantage", () => {
  it("rounds the measured production example to 1.4 times slower", () => {
    const value = summary(
      { fine_tuned: 1, comparison: 1 },
      { fine_tuned: 35.19353687545304, comparison: 50.6595658693694 },
    );
    expect(speedAdvantage(value)).toEqual({
      tone: "bad",
      label: "1.4× slower",
    });
    expect(outputSpeed(value)).toBe("35.2 vs 50.7 output tokens/s");
  });

  it("reads a slower fine-tuned model as bad", () => {
    expect(
      speedAdvantage(
        summary(
          { fine_tuned: 1, comparison: 1 },
          { fine_tuned: 50, comparison: 100 },
        ),
      ),
    ).toEqual({ tone: "bad", label: "2.0× slower" });
  });

  it("shows n/a when the comparison speed is zero", () => {
    expect(
      speedAdvantage(
        summary(
          { fine_tuned: 1, comparison: 1 },
          { fine_tuned: 50, comparison: 0 },
        ),
      ),
    ).toEqual({ tone: "neutral", label: "n/a" });
  });
});

describe("costPer1kRequests", () => {
  it("scales both per-request costs to 1,000 requests", () => {
    expect(
      costPer1kRequests(
        summary(
          { fine_tuned: 57_600, comparison: 835_000 },
          { fine_tuned: 1, comparison: 1 },
        ),
      ),
    ).toBe("$0.0576 vs $0.835 per 1k requests");
  });
});

describe("outputSpeed", () => {
  it("shows the fine-tuned speed before the comparison speed", () => {
    expect(
      outputSpeed(
        summary(
          { fine_tuned: 1, comparison: 1 },
          { fine_tuned: 112, comparison: 58 },
        ),
      ),
    ).toBe("112.0 vs 58.0 output tokens/s");
  });
});

it("shows placeholder Qwen rates while preserving unknown historical cost", () => {
  const value = {
    ...summary(
      { fine_tuned: 1, comparison: 1 },
      { fine_tuned: 1, comparison: 1 },
    ),
    comparison_model_id: "Qwen/Qwen3-0.6B",
    cost_per_request_nano_usd: null,
  };
  value.vs_comparison = {
    ...value.vs_comparison,
    comparator_model_id: "Qwen/Qwen3-0.6B",
  };
  expect(costAdvantage(value)).toEqual({
    tone: "neutral",
    label: "$0.05 / $0.10",
  });
  expect(costPer1kRequests(value)).toContain(
    "Historical request costs were not recorded",
  );
  expect(value.cost_per_request_nano_usd).toBeNull();
  expect(
    costAdvantage({ ...value, comparison_model_id: "another/model" }).label,
  ).toBe("n/a");
});
