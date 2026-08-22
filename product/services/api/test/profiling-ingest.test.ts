import { randomUUID } from "node:crypto";

import type { ProfilingEventBatch } from "@gradiated/contracts";
import type { ProfilingWriter } from "@gradiated/control";
import { describe, expect, it } from "vitest";

import { createProfilingIngestApp } from "../src/profiling-ingest.js";

const token = "profiling-test-token-with-at-least-32-characters";

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

describe("profiling ingestion", () => {
  it("rejects requests without the deployment token", async () => {
    const writer: ProfilingWriter = { insertBatch: async () => undefined };
    const response = await createProfilingIngestApp({ token, writer }).request(
      "/v1/profiling-events",
      { method: "POST", body: JSON.stringify(batch()) },
    );
    expect(response.status).toBe(401);
  });

  it("validates and inserts a batch", async () => {
    const inserted: ProfilingEventBatch[] = [];
    const writer: ProfilingWriter = {
      insertBatch: async (value) => {
        inserted.push(value);
      },
    };
    const payload = batch();
    const response = await createProfilingIngestApp({ token, writer }).request(
      "/v1/profiling-events",
      {
        method: "POST",
        headers: {
          authorization: `Bearer ${token}`,
          "content-type": "application/json",
        },
        body: JSON.stringify(payload),
      },
    );
    expect(response.status).toBe(204);
    expect(inserted).toEqual([payload]);
  });
});
