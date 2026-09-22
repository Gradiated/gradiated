import { describe, expect, it } from "vitest";
import { createServiceLogger } from "@gradiated/control";

describe("service diagnostics", () => {
  it("records correlation and diagnostic codes without raw error payloads", () => {
    const lines: string[] = [];
    const log = createServiceLogger("api", (line) => lines.push(line));
    const error = Object.assign(
      new Error("Bearer secret customer@example.com prompt=private"),
      { code: "ECONNRESET" },
    );
    log("error", "request_failed", {
      error,
      request_id: "0198ad73-a200-7000-8000-000000000002",
      route: "/api/v1/workspaces/:id",
      status: 500,
    });
    const entry = JSON.parse(lines[0]!);
    expect(entry.level).toBe("error");
    expect(entry.error_code).toBe("ECONNRESET");
    expect(entry.request_id).toBe("0198ad73-a200-7000-8000-000000000002");
    expect(entry.error_frames.length).toBeGreaterThan(0);
    expect(lines[0]).not.toMatch(/secret|customer@example|prompt=private/);
  });

  it("bounds outage volume and reports suppressed events", () => {
    const lines: string[] = [];
    let now = 0;
    const log = createServiceLogger(
      "worker",
      (line) => lines.push(line),
      () => now,
    );
    for (let i = 0; i < 100; i++)
      log("error", "dependency_error", { dependency: "valkey" });
    expect(lines).toHaveLength(10);
    now = 1_000;
    log("info", "dependency_recovered", { dependency: "valkey" });
    expect(JSON.parse(lines[10]!).suppressed_events).toBe(90);
  });
});
