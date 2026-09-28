import { describe, expect, it } from "vitest";

import { createServiceLogger } from "../src/service-logging.js";

const recordingLogger = (now: () => number = () => 0) => {
  const lines: string[] = [];
  const log = createServiceLogger("api", (line) => lines.push(line), now);
  const entries = () =>
    lines.map((line) => JSON.parse(line) as Record<string, unknown>);

  return { lines, log, entries };
};

const errorWithCode = (code: unknown) =>
  Object.assign(new Error("Bearer secret customer@example.com"), { code });

describe("service logging", () => {
  it("keeps correlation fields and drops messages, bodies and identities", () => {
    const { lines, log, entries } = recordingLogger();

    const fields = {
      error: errorWithCode("ECONNRESET"),
      request_id: "0198ad73-a200-7000-8000-000000000002",
      route: "/api/v1/workspaces/:id",
      status: 500,
      body: "prompt=private",
      email: "customer@example.com",
    };

    log("error", "request_failed", fields);

    expect(entries()[0]).toMatchObject({
      service: "api",
      level: "error",
      event: "request_failed",
      request_id: "0198ad73-a200-7000-8000-000000000002",
      route: "/api/v1/workspaces/:id",
      status: 500,
      error_type: "Error",
      error_code: "ECONNRESET",
      suppressed_events: 0,
    });
    expect(entries()[0]?.error_frames).toEqual(expect.any(Array));
    expect(lines[0]).not.toMatch(/secret|customer@example|prompt=private/);
  });

  it("keeps a Nomad allocation id and reason", () => {
    const { log, entries } = recordingLogger();

    log("warn", "nomad_allocation_unplaced", {
      allocation_id: "0f3c9a51-8d4b-4c1e-9a55-111111111111",
      model_id: "kev/kev-9b",
      reason: "node_not_registered",
    });

    expect(entries()[0]).toMatchObject({
      allocation_id: "0f3c9a51-8d4b-4c1e-9a55-111111111111",
      model_id: "kev/kev-9b",
      reason: "node_not_registered",
    });
  });

  it("drops a request ID that is not a UUID", () => {
    const { log, entries } = recordingLogger();

    log("info", "request", { request_id: "user@example.com" });

    expect(entries()[0]).not.toHaveProperty("request_id");
  });

  it.each([
    ["a PostgreSQL SQLSTATE", "23505", "23505"],
    ["a system error code", "ECONNREFUSED", "ECONNREFUSED"],
    ["an HTTP status code", 503, "503"],
    ["free text", "duplicate key for customer@example.com", undefined],
  ])("reports %s as a bounded diagnostic code", (_name, code, expected) => {
    const { log, entries } = recordingLogger();

    log("error", "dependency_error", { error: errorWithCode(code) });

    expect(entries()[0]?.error_code).toBe(expected);
  });

  it("names a thrown non-error value without printing it", () => {
    const { lines, log, entries } = recordingLogger();

    log("error", "dependency_error", { error: "customer@example.com" });

    expect(entries()[0]?.error_type).toBe("UnknownError");
    expect(lines[0]).not.toContain("customer@example.com");
  });

  it("emits ten events a second per level and reports the suppressed count on the next line of that level", () => {
    let now = 0;
    const { log, entries } = recordingLogger(() => now);

    for (let index = 0; index < 25; index += 1) {
      log("error", "dependency_error", { dependency: "valkey" });
    }
    now = 999;
    log("error", "dependency_error", { dependency: "valkey" });
    log("info", "dependency_recovered", { dependency: "valkey" });
    now = 1_000;
    log("error", "dependency_error", { dependency: "valkey" });
    log("error", "dependency_error", { dependency: "valkey" });

    const emitted = entries();

    expect(emitted).toHaveLength(13);
    expect(emitted[10]).toMatchObject({
      event: "dependency_recovered",
      suppressed_events: 0,
    });
    expect(emitted[11]).toMatchObject({
      event: "dependency_error",
      suppressed_events: 16,
      timestamp: "1970-01-01T00:00:01.000Z",
    });
    expect(emitted[12]?.suppressed_events).toBe(0);
  });

  it("rejects credentials disguised as resource IDs and ignores unknown fields", () => {
    const { lines, log, entries } = recordingLogger();

    log("warn", "request_completed", {
      api_key_id: "grad_DO_NOT_LOG_THIS",
      workspace_id: "not-a-uuid",
      ...{ authorization: "Bearer PRIVATE", secret: "PRIVATE" },
    });

    expect(lines[0]).not.toMatch(/DO_NOT_LOG_THIS|PRIVATE|not-a-uuid/);
    expect(entries()[0]).not.toHaveProperty("api_key_id");
  });

  it("does not let request volume suppress error diagnostics", () => {
    const { lines, log, entries } = recordingLogger();

    for (let i = 0; i < 20; i++) log("info", "request_completed");
    log("error", "request_failed", { error: new Error("private") });

    expect(lines).toHaveLength(11);
    expect(entries()[10]).toMatchObject({
      level: "error",
      event: "request_failed",
    });
  });
});
