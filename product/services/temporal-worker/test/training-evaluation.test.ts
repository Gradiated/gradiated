import { expect, it } from "vitest";
import {
  predictionsSchema,
  summarizePredictions,
} from "../src/training/evaluation.js";

const pair = {
  id: "example",
  group: "group",
  fine_tuned: { text: "fine", tokens: 10, seconds: 2 },
  comparison: { text: "base", tokens: 20, seconds: 2 },
};

it.each([
  [true, "A", "win"],
  [false, "B", "win"],
  [true, "B", "loss"],
  [false, "A", "loss"],
  [true, "TIE", "tie"],
  [false, "neither", "unresolved"],
] as const)(
  "decodes randomized order %s with decision %s",
  (fine_tuned_first, judgment, expected) => {
    const result = summarizePredictions(
      predictionsSchema.parse([{ ...pair, fine_tuned_first, judgment }]),
    );
    expect(result.fractions[expected]).toBe(1);
    expect(result.judging_method).toBe("randomized_single");
    expect(result.output_tokens_per_second).toEqual({
      fine_tuned: 5,
      comparison: 10,
    });
  },
);

it("weights independent groups equally and retains unresolved share", () => {
  const result = summarizePredictions(
    predictionsSchema.parse([
      { ...pair, fine_tuned_first: true, judgment: "A" },
      { ...pair, id: "second", fine_tuned_first: false, judgment: "B" },
      {
        ...pair,
        id: "third",
        group: "other",
        fine_tuned_first: true,
        judgment: "bad",
      },
    ]),
  );
  expect(result.holdout_groups).toBe(2);
  expect(result.holdout_examples).toBe(3);
  expect(result.fractions).toEqual({
    win: 1,
    tie: 0,
    loss: 0,
    unresolved: 0.5,
  });
});

it("reads frozen legacy runtimes without mislabelling their protocol", () => {
  const result = summarizePredictions(
    predictionsSchema.parse([
      { ...pair, judgments: ["A", "B"] },
      { ...pair, id: "second", group: "other", judgments: ["A", "A"] },
    ]),
  );
  expect(result.judging_method).toBe("both_orders");
  expect(result.fractions).toEqual({
    win: 1,
    tie: 0,
    loss: 0,
    unresolved: 0.5,
  });
});

it("rejects a single A/B judgment without an answer order", () => {
  expect(
    predictionsSchema.safeParse([{ ...pair, judgment: "A" }]).success,
  ).toBe(false);
});

it("estimates Qwen output cost without transferring the rate to another base", async () => {
  const { estimateOutputCost } = await import("../src/training/evaluation.js");
  const rows = predictionsSchema.parse([
    { ...pair, judgment: "TIE", fine_tuned_first: true },
  ]);
  expect(
    estimateOutputCost(rows, "Qwen/Qwen3-0.6B", "Qwen/Qwen3-0.6B"),
  ).toEqual({ fine_tuned: 1000, comparison: 2000 });
  expect(
    estimateOutputCost(rows, "another/base", "Qwen/Qwen3-0.6B"),
  ).toBeNull();
});

it("rounds mean output costs to integer nano-USD and handles empty results", async () => {
  const { estimateOutputCost } = await import("../src/training/evaluation.js");
  const rows = predictionsSchema.parse(
    [0, 0, 1].map((tokens, i) => ({
      ...pair,
      id: String(i),
      judgment: "TIE",
      fine_tuned_first: true,
      fine_tuned: { ...pair.fine_tuned, tokens },
      comparison: { ...pair.comparison, tokens: 1 - tokens },
    })),
  );

  expect(
    estimateOutputCost(rows, "Qwen/Qwen3-0.6B", "Qwen/Qwen3-0.6B"),
  ).toEqual({ fine_tuned: 33, comparison: 67 });
  expect(
    estimateOutputCost([], "Qwen/Qwen3-0.6B", "Qwen/Qwen3-0.6B"),
  ).toBeNull();
});
