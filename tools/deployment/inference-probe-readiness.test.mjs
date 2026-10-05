import { execFileSync } from "node:child_process";
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  checkInferenceProbeReadiness,
  readWorker,
} from "./inference-probe-readiness.mjs";

const observation = (success = 99, inventory = 99, id = "replica-a") => ({
  deployments: [{ id, modelId: "test/model" }],
  metrics: `gradiated_inference_probe_inventory_timestamp_seconds{service="worker"} ${inventory}\ngradiated_inference_probe_last_success_timestamp_seconds{model="test/model",deployment="${id}",service="worker"} ${success}\n`,
});
test("requires fresh successful real inference for every serving deployment", () => {
  assert.equal(
    checkInferenceProbeReadiness(
      [observation(), observation(98, 99, "replica-b")],
      100,
    ).size,
    2,
  );
  assert.throws(
    () =>
      checkInferenceProbeReadiness(
        [observation(), observation(0, 99, "replica-b")],
        100,
      ),
    /replica-b/,
  );
});
test("detects stopped monitoring separately from failed inference", () => {
  assert.throws(
    () => checkInferenceProbeReadiness([observation(99, 80)], 100),
    /discovery/,
  );
  assert.throws(
    () => checkInferenceProbeReadiness([observation(80)], 100),
    /successful public inference/,
  );
  assert.throws(() => checkInferenceProbeReadiness([], 100), /discovery/);
});
test("a standby or stale previous leader does not hide a healthy new leader", () => {
  assert.equal(
    checkInferenceProbeReadiness([observation(0, 0), observation()], 100).get(
      "replica-a",
    ),
    99,
  );
});

test("the diagnostic loads control from the deployed product filesystem and reads real metrics", () => {
  const cwd = mkdtempSync(join(tmpdir(), "inference-probe-reader-"));
  try {
    mkdirSync(join(cwd, "packages/control/dist"), { recursive: true });
    writeFileSync(
      join(cwd, "package.json"),
      JSON.stringify({ type: "module" }),
    );
    writeFileSync(
      join(cwd, "packages/control/dist/index.js"),
      `
      export const createControlDatabase = () => ({ database: {}, pool: { end: async () => {} } });
      export const createNomadDeploymentStore = () => ({ replicas: async () => [{ id: "replica-a", modelId: "test/model" }] });
    `,
    );
    const output = execFileSync(
      process.execPath,
      [
        "--input-type=module",
        "-e",
        `
      globalThis.fetch = async () => new Response("synthetic-metrics");
      ${readWorker}
    `,
      ],
      { cwd, encoding: "utf8", timeout: 5000 },
    );
    assert.deepEqual(JSON.parse(output), {
      deployments: [{ id: "replica-a", modelId: "test/model" }],
      metrics: "synthetic-metrics",
    });
  } finally {
    rmSync(cwd, { recursive: true, force: true });
  }
});
