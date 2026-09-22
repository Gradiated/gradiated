import { describe, expect, it, vi } from "vitest";
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
    log("error", "dependency_error", { dependency: "valkey" });
    expect(JSON.parse(lines[10]!).suppressed_events).toBe(90);
  });
});

it("keeps resource IDs on authenticated requests without logging keys or identities", async () => {
  const { createApp } = await import("../src/app.js");
  const {
    authenticated,
    organizationId,
    workspaceId,
    apiKeyId,
    workspaceService,
  } = await import("./support.js");
  const lines: string[] = [];
  const spy = vi
    .spyOn(console, "log")
    .mockImplementation((line: string) => lines.push(line));
  try {
    const app = createApp({
      auth: authenticated,
      services: { workspaces: workspaceService() },
    });
    const path = `/api/v1/organizations/${organizationId}/workspaces/${workspaceId}/api-keys/${apiKeyId}`;
    await app.request(path, {
      method: "DELETE",
      headers: { authorization: "Bearer DO_NOT_LOG_THIS" },
    });
    const event = lines
      .map((line) => JSON.parse(line))
      .find((line) => line.event === "request_completed");
    expect(event).toMatchObject({
      organization_id: organizationId,
      workspace_id: workspaceId,
      api_key_id: apiKeyId,
      context_source: "authenticated_session_requested_resource",
      status: 204,
    });
    expect(lines.join("\n")).not.toMatch(
      /DO_NOT_LOG_THIS|ada@example|Ada Lovelace/,
    );
    lines.length = 0;
    const created = await app.request(
      `/api/v1/organizations/${organizationId}/workspaces/${workspaceId}/api-keys`,
      {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ name: "PRIVATE_KEY_NAME" }),
      },
    );
    const createdBody = await created.json();
    expect(created.status).toBe(201);
    expect(
      lines
        .map((line) => JSON.parse(line))
        .find((line) => line.event === "request_completed"),
    ).toMatchObject({ api_key_id: apiKeyId });
    expect(lines.join("\n")).not.toContain(createdBody.secret);
    expect(lines.join("\n")).not.toContain("PRIVATE_KEY_NAME");
    lines.length = 0;
    await createApp().request(path, { method: "DELETE" });
    const denied = lines
      .map((line) => JSON.parse(line))
      .find((line) => line.event === "request_completed");
    expect(denied.organization_id).toBeUndefined();
    expect(denied.workspace_id).toBeUndefined();
    expect(denied.api_key_id).toBeUndefined();
  } finally {
    spy.mockRestore();
  }
});

it("rejects credentials disguised as resource IDs and ignores unknown fields", () => {
  const lines: string[] = [];
  const log = createServiceLogger("api", (line) => lines.push(line));
  const unsafe = {
    api_key_id: "grad_DO_NOT_LOG_THIS",
    workspace_id: "not-a-uuid",
    authorization: "Bearer PRIVATE",
    secret: "PRIVATE",
  };
  log("warn", "request_completed", unsafe);
  expect(lines[0]).not.toMatch(/DO_NOT_LOG_THIS|PRIVATE|not-a-uuid/);
  expect(JSON.parse(lines[0]!)).not.toHaveProperty("api_key_id");
});

it("does not let normal request volume suppress error diagnostics", () => {
  const lines: string[] = [];
  const log = createServiceLogger("api", (line) => lines.push(line));
  for (let i = 0; i < 20; i++) log("info", "request_completed");
  log("error", "request_failed", { error: new Error("private") });
  expect(lines).toHaveLength(11);
  expect(JSON.parse(lines[10]!)).toMatchObject({
    level: "error",
    event: "request_failed",
  });
});
