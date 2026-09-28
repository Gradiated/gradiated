import { servedReleaseDigest } from "@gradiated/control";
import { describe, expect, it } from "vitest";

import { countReadyReplicas } from "../src/replica-readiness.js";

const release = {
  schema_version: 1 as const,
  runtime_revision: "r1",
  model_path: "vendor/model",
  model_revision: "model-revision",
  tokenizer_path: "vendor/tokenizer",
  tokenizer_revision: "tokenizer-revision",
};
const now = Date.parse("2026-09-28T12:00:00Z");
const report = (overrides: Record<string, unknown> = {}) =>
  JSON.stringify({
    healthy: true,
    accepting_requests: true,
    runtime_revision: "r1",
    received_at: new Date(now - 5_000).toISOString(),
    ...overrides,
  });

describe("replica readiness", () => {
  it("counts only fresh, healthy reports for the replica's release", async () => {
    const statuses: Record<string, Record<string, string>> = {
      [servedReleaseDigest(release)]: {
        ready: report(),
        unhealthy: report({ healthy: false }),
        stale: report({ received_at: new Date(now - 61_000).toISOString() }),
        wrongRevision: report({ runtime_revision: "r0" }),
        garbled: "{",
      },
    };
    const replicas = [
      "ready",
      "unhealthy",
      "stale",
      "wrongRevision",
      "garbled",
      "silent",
    ].map((id) => ({ id, modelId: "kev/kev-9b", release }));

    const counts = await countReadyReplicas(
      replicas,
      async (digest) => statuses[digest] ?? {},
      now,
    );

    expect(counts).toEqual({ "kev/kev-9b": { replicas: 6, ready: 1 } });
  });
});
