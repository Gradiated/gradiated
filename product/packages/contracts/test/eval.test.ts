import { describe, expect, it } from "vitest";
import { EvalSchema } from "../src/eval.js";

const valid = () => ({
  schema: "gradiated.eval/1",
  id: "support",
  title: "Support actions",
  created_at: "2026-11-20T12:00:00Z",
  metrics: [{ id: "correct", name: "Passed", kind: "pass" }],
  primary_metric: "correct",
  models: [
    { id: "mini", name: "support-mini" },
    { id: "frontier", name: "Frontier model" },
  ],
  cases: [{ id: "case-1", title: "Refund a duplicate charge" }],
  rollouts: [
    {
      id: "r1",
      case_id: "case-1",
      model_id: "mini",
      scores: { correct: true },
    },
    {
      id: "r2",
      case_id: "case-1",
      model_id: "frontier",
      status: "error",
      error: "Provider timeout",
      scores: { correct: null },
    },
  ],
});

describe("EvalSchema", () => {
  it("accepts a minimal eval and fills defaults", () => {
    const parsed = EvalSchema.parse(valid());

    expect(parsed.rollouts[0]).toMatchObject({
      status: "completed",
      checks: [],
      messages: [],
    });
    expect(parsed.cases[0]).toMatchObject({ tags: {}, expected: [] });
    expect(parsed.models[0]!.kind).toBe("model");
  });

  it("rejects references to unknown cases, models and metrics", () => {
    const input = valid();
    input.rollouts[0]!.case_id = "case-9";
    input.rollouts[1]!.model_id = "other";
    input.primary_metric = "quality";

    const messages = EvalSchema.safeParse(input).error?.issues.map(
      (issue) => issue.message,
    );
    expect(messages).toEqual(
      expect.arrayContaining([
        "Unknown case case-9.",
        "Unknown model other.",
        "primary_metric must name a metric.",
      ]),
    );
  });

  it("needs two models to compare", () => {
    const input = valid();
    input.models = input.models.slice(0, 1);

    expect(EvalSchema.safeParse(input).success).toBe(false);
  });

  it("rejects duplicate rollout IDs", () => {
    const input = valid();
    input.rollouts[1]!.id = "r1";

    expect(EvalSchema.safeParse(input).success).toBe(false);
  });
});
