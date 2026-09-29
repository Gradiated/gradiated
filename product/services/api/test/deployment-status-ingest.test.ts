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

const runpodToken = "runpod-test-token-with-at-least-32-characters";
const nomadToken = "nomad-test-token-with-at-least-32-characters!";
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
    tokens: new Map([
      ["runpod", runpodToken],
      ["nomad", nomadToken],
    ]),
    service,
  });

const send = (
  app: Hono,
  body: string,
  authorization = `Bearer ${runpodToken}`,
) =>
  app.request(path, {
    method: "POST",
    headers: { authorization, "content-type": "application/json" },
    body,
  });

afterEach(() => {
  vi.restoreAllMocks();
});

describe("deployment status ingestion", () => {
  it("accepts a valid status for the token's provider", async () => {
    const reports: Array<[string, DeploymentStatusReport]> = [];
    const payload = {
      ...report(),
      deployment_id: "a4d51466-8782-bf13-3b97-b8a07ad79c26",
    };
    const app = createIngestApp({
      report: async (provider, value) => {
        reports.push([provider, value]);
      },
    });

    const runpod = await send(app, JSON.stringify(payload));
    const nomad = await send(
      app,
      JSON.stringify(payload),
      `Bearer ${nomadToken}`,
    );

    expect(runpod.status).toBe(204);
    expect(nomad.status).toBe(204);
    expect(reports).toEqual([
      ["runpod", payload],
      ["nomad", payload],
    ]);
  });

  it("rejects an unknown token", async () => {
    const response = await send(
      createIngestApp(),
      JSON.stringify(report()),
      `Bearer ${"x".repeat(runpodToken.length)}`,
    );

    expect(response.status).toBe(401);
    await expect(response.json()).resolves.toEqual({ error: "unauthorized" });
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
