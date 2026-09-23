import { describe, expect, it } from "vitest";

import { copyLabel } from "@/hooks/use-copy-to-clipboard";

describe("copyLabel", () => {
  it("shows the idle label before a copy", () => {
    expect(copyLabel("idle", "Copy key")).toBe("Copy key");
  });

  it("confirms a successful copy", () => {
    expect(copyLabel("copied", "Copy key")).toBe("Copied");
  });

  it("reports a failed copy", () => {
    expect(copyLabel("failed", "Copy key")).toBe("Copy failed");
  });
});
