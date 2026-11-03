import { describe, expect, it } from "vitest";
import type { components } from "@/api/schema";
import {
  currentVersion,
  versionsForTask,
  latestVersionEvaluation,
} from "@/store/fine-tuning-views";

const version = (
  id: string,
  production = false,
): components["schemas"]["TaskVersion"] => ({
  id,
  name: `task-${id}`,
  task: "task",
  training_run_id: `run-${id}`,
  base_model_id: "base",
  adapter: {
    format: "peft_lora",
    artifact_uri: "s3://bucket/adapter",
    sha256: "a".repeat(64),
    size_bytes: 100,
    rank: 8,
  },
  status: "available",
  is_production: production,
  created_at: "2026-09-01T00:00:00Z",
});

describe("versionsForTask", () => {
  it("keeps published versions visible before evaluation is available", () => {
    const versions = versionsForTask([version("new")], []);

    expect(versions).toHaveLength(1);
    expect(versions[0]).toMatchObject({ id: "new", summary: null });
  });
});

describe("currentVersion", () => {
  it.each([true, false])(
    "prefers production when present: %s",
    (production) => {
      const versions = versionsForTask(
        [version("new"), version("old", production)],
        [],
      );

      expect(currentVersion(versions)?.id).toBe(production ? "old" : "new");
      expect(currentVersion([])).toBeUndefined();
    },
  );
});

describe("latestVersionEvaluation", () => {
  const evaluation = {
    holdout_groups: 1,
    holdout_examples: 1,
    comparison_model_id: "Qwen/Qwen3-0.6B",
    judge_model_id: "Qwen/Qwen3-0.6B",
    vs_comparison: {
      comparator_model_id: "Qwen/Qwen3-0.6B",
      win: 1,
      tie: 0,
      loss: 0,
      unresolved: 0,
    },
    cost_per_request_nano_usd: null,
    output_tokens_per_second: { fine_tuned: 1, comparison: 1 },
    error_rate: 0,
  } satisfies components["schemas"]["RunEvaluation"];
  it("shows metrics only for the displayed version's run", () => {
    const latest_run = { id: "newer-run", evaluation };
    expect(
      latestVersionEvaluation({
        latest_run,
        latest_version: { training_run_id: "newer-run" },
      }),
    ).toBe(evaluation);
    expect(
      latestVersionEvaluation({
        latest_run,
        latest_version: { training_run_id: "older-published-run" },
      }),
    ).toBeNull();
    expect(
      latestVersionEvaluation({
        latest_run,
        latest_version: { training_run_id: null },
      }),
    ).toBeNull();
  });
  it("preserves metrics for responses without a latest-version field", () => {
    expect(
      latestVersionEvaluation({ latest_run: { id: "legacy-run", evaluation } }),
    ).toBe(evaluation);
    expect(latestVersionEvaluation({ latest_run: null })).toBeNull();
  });
});
