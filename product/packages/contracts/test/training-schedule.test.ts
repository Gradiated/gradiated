import { expect, it } from "vitest";
import { nextTrainingTime } from "../src/training-schedule.js";
import {
  COMPARISON_MODELS,
  TRAINING_BASE_MODELS,
} from "../src/model-catalog.js";

it("shows a weekly UTC occurrence and advances at the exact boundary", () => {
  expect(
    nextTrainingTime(
      "0 3 * * MON",
      new Date("2026-10-01T23:00:00Z"),
    )?.toISOString(),
  ).toBe("2026-10-05T03:00:00.000Z");
  expect(
    nextTrainingTime(
      "0 3 * * MON",
      new Date("2026-10-05T03:00:00Z"),
    )?.toISOString(),
  ).toBe("2026-10-12T03:00:00.000Z");
});

it("matches Temporal's AND semantics when both day fields are restricted", () => {
  expect(
    nextTrainingTime(
      "0 3 1 * MON",
      new Date("2026-10-01T00:00:00Z"),
    )?.toISOString(),
  ).toBe("2027-02-01T03:00:00.000Z");
});

it("handles disabled, invalid and impossible schedules", () => {
  expect(nextTrainingTime(null)).toBeNull();
  expect(nextTrainingTime("invalid")).toBeNull();
  expect(nextTrainingTime("0 0 31 FEB *")).toBeNull();
});

it("separates training bases from comparison-only hosted and frontier models", () => {
  expect(TRAINING_BASE_MODELS.map(({ id }) => id)).toEqual([
    "Qwen/Qwen3-0.6B",
    "Qwen/Qwen3-1.7B",
    "Qwen/Qwen3-4B",
    "Qwen/Qwen3-8B",
    "Qwen/Qwen3-14B",
    "Qwen/Qwen3-32B",
  ]);
  const ids = COMPARISON_MODELS.map(({ id }) => id);
  expect(ids).toContain("openai/gpt-6-astra");
  expect(ids).toContain("anthropic/claude-opus-5-5");
  expect(ids).toContain("deepseek/deepseek-v4.1-flash-1017");
  expect(ids).toContain("deepseek/deepseek-v4.1-flash");
  expect(ids).not.toContain("jaredpalmer/kev-9b");
});

it("rejects Kev as a comparison model in task updates", async () => {
  const { UpdateTaskSchema } = await import("../src/training.js");
  expect(
    UpdateTaskSchema.safeParse({ comparison_model_id: "jaredpalmer/kev-9b" })
      .success,
  ).toBe(false);
  expect(
    UpdateTaskSchema.safeParse({ comparison_model_id: "Qwen/Qwen3-0.6B" })
      .success,
  ).toBe(true);
});

it("preserves saved Dealign judge IDs while offering the renamed model", async () => {
  const { EvaluationJudgeSchema } = await import("../src/training.js");
  const { modelSupportedUses, modelDisplayName } =
    await import("../src/model-catalog.js");
  const legacy = "dealignai/glm-5.3-flash-uncensored-nvfp4";
  const renamed = "dealignai/glm-5.3-flash-uncensored";

  expect(EvaluationJudgeSchema.parse(legacy)).toBe(legacy);
  expect(EvaluationJudgeSchema.parse(renamed)).toBe(renamed);
  expect(modelSupportedUses(legacy)).toContain("comparison");
  expect(modelDisplayName(legacy)).toBe("GLM-5.3 Flash Uncensored");
  expect(COMPARISON_MODELS.map(({ id }) => id)).toContain(renamed);
  expect(COMPARISON_MODELS.map(({ id }) => id)).not.toContain(legacy);
});
