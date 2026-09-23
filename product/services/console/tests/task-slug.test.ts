import { describe, expect, it } from "vitest";

import { slugifyTaskInput, taskSlugError } from "@/lib/task-slug";

describe("slugifyTaskInput", () => {
  it("lowercases, hyphenates whitespace and drops invalid characters", () => {
    expect(slugifyTaskInput("  Support Triage!! ")).toBe("support-triage-");
  });

  it("drops leading separators and caps the length at 64", () => {
    expect(slugifyTaskInput("._-task")).toBe("task");
    expect(slugifyTaskInput("a".repeat(80))).toHaveLength(64);
  });
});

describe("taskSlugError", () => {
  it("accepts a valid slug", () => {
    expect(taskSlugError("support-triage.v2_a")).toBeNull();
  });

  it("asks for a name when empty", () => {
    expect(taskSlugError("")).toBe("Enter a task name.");
  });

  it.each(["-task", "Task", "task name", "a".repeat(65)])(
    "rejects %j",
    (value) => {
      expect(taskSlugError(value)).toMatch(/^Lowercase letters/);
    },
  );
});
