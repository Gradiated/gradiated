import { describe, expect, it } from "vitest";

import {
  initiallyOpenStage,
  stepState,
  stepsFor,
} from "@/components/fine-tuning/stage-steps";
import { STAGE_ORDER } from "@/store/fine-tuning-types";

describe("stepState", () => {
  it.each([
    ["training", "training", ["queued"], "current"],
    ["queued", "training", ["queued"], "done"],
    ["publishing", "training", ["queued"], "pending"],
    ["failed", "failed", ["queued"], "failed"],
    ["cancelled", "cancelled", ["queued"], "cancelled"],
    ["training", "failed", ["queued"], "skipped"],
    ["succeeded", "succeeded", ["queued", "succeeded"], "done"],
  ] as const)(
    "marks %s during %s after %j as %s",
    (stage, runStage, visited, expected) => {
      expect(stepState(stage, runStage, [...visited])).toBe(expected);
    },
  );
});

describe("stepsFor", () => {
  it("lists every stage for a run that has not stopped", () => {
    expect(stepsFor("training", ["queued"])).toBe(STAGE_ORDER);
  });

  it("places a stopped stage after the visited stages and drops success", () => {
    expect(stepsFor("failed", ["queued", "building_dataset"])).toEqual([
      "queued",
      "building_dataset",
      "failed",
      "awaiting_capacity",
      "training",
      "verifying",
      "publishing",
      "evaluating",
    ]);
  });
});

describe("initiallyOpenStage", () => {
  it.each([
    ["training", "training"],
    ["cancelling", "cancelling"],
    ["failed", "failed"],
    ["cancelled", "cancelled"],
    ["succeeded", null],
  ] as const)("opens %s as %s", (runStage, expected) => {
    expect(initiallyOpenStage(runStage)).toBe(expected);
  });
});
