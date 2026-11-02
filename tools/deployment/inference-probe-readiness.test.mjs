import assert from "node:assert/strict";
import { test } from "node:test";
import {
  checkInferenceProbeReadiness,
  readInferenceProbeObservations,
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
    () => checkInferenceProbeReadiness([observation(24)], 100),
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

const pods = ["worker-a", "worker-b"].map((name) => ({ metadata: { name } }));

test("reads inventory once and every worker's metrics through the Kubernetes API", async () => {
  const paths = [];
  const expected = observation();
  const observations = await readInferenceProbeObservations(
    pods,
    async (path) => {
      paths.push(path);
      return path.endsWith("/metrics/targets/inference")
        ? JSON.stringify(expected.deployments)
        : path.includes("worker-a")
          ? observation(0, 0).metrics
          : expected.metrics;
    },
  );

  assert.deepEqual(paths, [
    "/api/v1/namespaces/gradiated/pods/http:worker-a:9464/proxy/metrics/targets/inference",
    "/api/v1/namespaces/gradiated/pods/http:worker-a:9464/proxy/metrics",
    "/api/v1/namespaces/gradiated/pods/http:worker-b:9464/proxy/metrics",
  ]);
  assert.equal(checkInferenceProbeReadiness(observations, 100).size, 1);
});

test("inventory includes deployments that have no probe metrics yet", async () => {
  const observations = await readInferenceProbeObservations(
    pods,
    async (path) =>
      path.endsWith("/metrics/targets/inference")
        ? JSON.stringify([
            ...observation().deployments,
            { id: "replica-missing", modelId: "test/new-model" },
          ])
        : observation().metrics,
  );

  assert.throws(
    () => checkInferenceProbeReadiness(observations, 100),
    /replica-missing/,
  );
});

test("fails closed on unavailable inventory or worker metrics", async () => {
  await assert.rejects(
    readInferenceProbeObservations([], async () => ""),
    /No ready workers/,
  );
  await assert.rejects(
    readInferenceProbeObservations(pods, async () => {
      throw new Error("inventory unavailable");
    }),
    /inventory unavailable/,
  );
  await assert.rejects(
    readInferenceProbeObservations(pods, async (path) => {
      if (path.endsWith("/metrics/targets/inference"))
        return JSON.stringify(observation().deployments);

      throw new Error("metrics unavailable");
    }),
    /metrics unavailable/,
  );
});

test("rejects malformed inventory", async () => {
  for (const inventory of [{}, [null], [{ id: "replica-a" }]]) {
    await assert.rejects(
      readInferenceProbeObservations(pods, async () =>
        JSON.stringify(inventory),
      ),
      /Invalid serving inference inventory/,
    );
  }
});

test("accepts minute-spaced deployment successes with deadline and scrape allowance", () => {
  assert.equal(checkInferenceProbeReadiness([observation(25)], 100).size, 1);
  assert.throws(
    () => checkInferenceProbeReadiness([observation(24)], 100),
    /successful public inference/,
  );
});
