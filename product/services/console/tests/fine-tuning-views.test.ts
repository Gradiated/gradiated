import { describe, expect, it } from "vitest";
import type { components } from "@/api/schema";
import { currentVersion, versionsForTask } from "@/store/fine-tuning-views";

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
