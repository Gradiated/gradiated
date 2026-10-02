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
  expect(TRAINING_BASE_MODELS.map(({ id }) => id)).toEqual(["Qwen/Qwen3-0.6B"]);
  const ids = COMPARISON_MODELS.map(({ id }) => id);
  expect(ids).toContain("openai/gpt-6-astra");
  expect(ids).toContain("anthropic/claude-opus-5-5");
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
