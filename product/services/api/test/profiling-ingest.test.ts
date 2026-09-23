import { randomUUID } from "node:crypto";

import type { ProfilingEventBatch } from "@gradiated/contracts";
import type { ProfilingWriter } from "@gradiated/control";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createProfilingIngestApp } from "../src/ingest/profiling.js";
import { captureServiceLogs } from "./support.js";

const token = "profiling-test-token-with-at-least-32-characters";
const path = "/v1/profiling-events";

const batch = (): ProfilingEventBatch => ({
  schema_version: 1,
  batch_id: randomUUID(),
  deployment_id: randomUUID(),
  model_id: "google/gemma-4-31B-it",
  runtime_revision: "sha256:test",
  events: [
    {
      id: randomUUID(),
      observed_at: new Date().toISOString(),
      event_type: "gpu.sample",
      properties: { utilization_percent: 42 },
    },
  ],
});

const ingest = (
  body: string,
  {
    authorization = `Bearer ${token}`,
    writer = { insertBatch: async () => undefined },
  }: { authorization?: string; writer?: ProfilingWriter } = {},
) =>
  createProfilingIngestApp({ token, writer }).request(path, {
    method: "POST",
    headers: { authorization, "content-type": "application/json" },
    body,
  });

afterEach(() => {
  vi.restoreAllMocks();
});

describe("profiling ingestion", () => {
  it("validates and inserts a batch", async () => {
    const inserted: ProfilingEventBatch[] = [];
    const payload = batch();

    const response = await ingest(JSON.stringify(payload), {
      writer: {
        insertBatch: async (value) => {
          inserted.push(value);
        },
      },
    });

    expect(response.status).toBe(204);
    expect(inserted).toEqual([payload]);
  });

  it.each([
    { name: "a missing token", authorization: "" },
    { name: "a non-Bearer scheme", authorization: `Basic ${token}` },
    {
      name: "a wrong token of the same length",
      authorization: `Bearer ${"x".repeat(token.length)}`,
    },
  ])("rejects $name", async ({ authorization }) => {
    const response = await ingest(JSON.stringify(batch()), { authorization });

    expect(response.status).toBe(401);
    await expect(response.json()).resolves.toEqual({ error: "unauthorized" });
  });

  it("rejects malformed JSON", async () => {
    const response = await ingest("{");

    expect(response.status).toBe(400);
    await expect(response.json()).resolves.toEqual({ error: "invalid_json" });
  });

  it("rejects an invalid batch with its issues", async () => {
    const response = await ingest(JSON.stringify({ ...batch(), events: [] }));

    expect(response.status).toBe(422);
    await expect(response.json()).resolves.toMatchObject({
      error: "invalid_batch",
      issues: [{ path: "events" }],
    });
  });

  it("rejects a body over 4 MiB", async () => {
    const response = await ingest("x".repeat(4 * 1024 * 1024 + 1));

    expect(response.status).toBe(413);
    await expect(response.json()).resolves.toEqual({
      error: "payload_too_large",
    });
  });

  it("logs a writer failure without the payload", async () => {
    const logs = captureServiceLogs();
    const payload = batch();

    const response = await ingest(JSON.stringify(payload), {
      writer: {
        insertBatch: async () => {
          throw new Error(`insert failed for ${payload.batch_id}`);
        },
      },
    });

    expect(response.status).toBe(500);
    await expect(response.json()).resolves.toEqual({ error: "internal_error" });
    expect(logs.events()).toEqual([
      expect.objectContaining({
        event: "ingest_failed",
        route: path,
        error_type: "Error",
      }),
    ]);
    expect(logs.lines().join("\n")).not.toContain(payload.batch_id);
  });
});
