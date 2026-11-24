import { randomUUID } from "node:crypto";

import type { DeploymentStatusReport } from "@gradiated/contracts";
import {
  DeploymentStatusError,
  type DeploymentStatusService,
} from "@gradiated/control";
import { Hono } from "hono";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createDeploymentStatusIngestApp } from "../src/ingest/deployment-status.js";
import { captureServiceLogs } from "./support.js";

const path = "/v1/deployment-status";

const report = (): DeploymentStatusReport => ({
  schema_version: 1,
  deployment_id: randomUUID(),
  runtime_revision: "vllm-revision",
  healthy: true,
  accepting_requests: true,
  reason_code: null,
});

const createIngestApp = (
  service: DeploymentStatusService = { report: async () => undefined },
) =>
  createDeploymentStatusIngestApp({
    providers: ["runpod"],
    service,
  });

const send = (app: Hono, body: string) =>
  app.request(path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body,
  });

afterEach(() => {
  vi.restoreAllMocks();
});

describe("deployment status ingestion", () => {
  it("uses the configured provider on the private listener without a bearer token", async () => {
    const reportStatus = vi.fn(async () => undefined);
    const app = createDeploymentStatusIngestApp({
      providers: ["runpod"],
      service: { report: reportStatus },
    });
    const payload = report();
    const response = await app.request(path, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
    expect(response.status).toBe(204);
    expect(reportStatus).toHaveBeenCalledWith(["runpod"], payload);
  });

  it("passes the runtime active request limit to the status service", async () => {
    const reportStatus = vi.fn(async () => undefined);
    const payload = { ...report(), active_requests: 4 };

    const response = await send(
      createIngestApp({ report: reportStatus }),
      JSON.stringify(payload),
    );

    expect(response.status).toBe(204);
    expect(reportStatus).toHaveBeenCalledWith(["runpod"], payload);
  });

  it("rejects malformed JSON", async () => {
    const response = await send(createIngestApp(), "{");

    expect(response.status).toBe(400);
    await expect(response.json()).resolves.toEqual({ error: "invalid_json" });
  });

  it("rejects a report that fails the schema", async () => {
    const response = await send(
      createIngestApp(),
      JSON.stringify({ ...report(), healthy: "yes" }),
    );

    expect(response.status).toBe(422);
    await expect(response.json()).resolves.toEqual({ error: "invalid_status" });
  });

  it("rejects a body over 64 KiB", async () => {
    const response = await send(createIngestApp(), "x".repeat(64 * 1024 + 1));

    expect(response.status).toBe(413);
  });

  it("limits only its own route when mounted into another app", async () => {
    const host = new Hono();
    host.route("/", createIngestApp());
    host.post("/other", (context) => context.body(null, 204));

    const response = await host.request("/other", {
      method: "POST",
      body: "x".repeat(64 * 1024 + 1),
    });

    expect(response.status).toBe(204);
  });

  it.each([
    { code: "deployment_not_found", status: 404 },
    { code: "provider_mismatch", status: 403 },
    { code: "runtime_revision_mismatch", status: 403 },
  ] as const)(
    "maps $code to $status and logs why",
    async ({ code, status }) => {
      const logs = captureServiceLogs();
      const payload = report();
      const app = createIngestApp({
        report: async () => {
          throw new DeploymentStatusError(code);
        },
      });

      const response = await send(app, JSON.stringify(payload));

      expect(response.status).toBe(status);
      await expect(response.json()).resolves.toEqual({ error: code });
      expect(logs.events()).toEqual([
        expect.objectContaining({
          event: "deployment_status_rejected",
          deployment_id: payload.deployment_id,
          reason: code,
        }),
      ]);
    },
  );

  it("logs an unexpected service failure and returns a bounded error", async () => {
    const logs = captureServiceLogs();
    const payload = report();
    const app = createIngestApp({
      report: async () => {
        throw new Error(`write failed for ${payload.deployment_id}`);
      },
    });

    const response = await send(app, JSON.stringify(payload));

    expect(response.status).toBe(500);
    await expect(response.json()).resolves.toEqual({ error: "internal_error" });
    expect(logs.events()).toEqual([
      expect.objectContaining({
        event: "ingest_failed",
        route: path,
        error_type: "Error",
      }),
    ]);
    expect(logs.lines().join("\n")).not.toContain(payload.deployment_id);
  });
});
