import assert from "node:assert/strict";
import test from "node:test";
import { rolloutReady, waitRollouts } from "./wait-rollouts.mjs";

const deployment = { metadata: { generation: 7 } };
const ready = () => ({
  metadata: { name: "api", generation: 3 },
  spec: { replicas: 3 },
  status: {
    workloadObservedGeneration: 7,
    observedGeneration: "3",
    phase: "Healthy",
    currentPodHash: "new",
    stableRS: "new",
    updatedReplicas: 3,
    availableReplicas: 3,
  },
});

test("only the fully promoted current workload qualifies", () => {
  assert.equal(rolloutReady(ready(), deployment), true);
  const serializedGeneration = ready();
  serializedGeneration.status.workloadObservedGeneration = "7";
  assert.equal(rolloutReady(serializedGeneration, deployment), true);
  for (const patch of [
    { workloadObservedGeneration: 6 },
    { observedGeneration: "2" },
    { phase: "Progressing" },
    { stableRS: "old" },
    { updatedReplicas: 2 },
    { availableReplicas: 2 },
    { currentPodHash: undefined },
  ]) {
    const rollout = ready();
    Object.assign(rollout.status, patch);
    assert.equal(
      rolloutReady(rollout, deployment),
      false,
      JSON.stringify(patch),
    );
  }
});

test("abort fails the release rather than publishing the console", () => {
  const rollout = ready();
  rollout.status.abort = true;
  assert.throws(() => rolloutReady(rollout, deployment), /aborted/);
  rollout.status.workloadObservedGeneration = 6;
  assert.equal(
    rolloutReady(rollout, deployment),
    false,
    "old abort must not reject a new hotfix",
  );
});

test("waits for every service and times out if one remains paused", async () => {
  let time = 0;
  await assert.rejects(
    waitRollouts({
      read: async (kind, name) =>
        kind === "deployment"
          ? deployment
          : {
              ...ready(),
              status: {
                ...ready().status,
                phase: name === "proxy" ? "Paused" : "Healthy",
              },
            },
      now: () => time,
      wait: async () => {
        time += 20 * 60 * 1000;
      },
    }),
    /proxy/,
  );
});

test("transient API failures are retried without accepting stale state", async () => {
  let reads = 0;
  await waitRollouts({
    read: async (kind) => {
      if (++reads === 1) throw new Error("NotFound");
      return kind === "deployment" ? deployment : ready();
    },
    wait: async () => {},
  });
  assert.ok(reads > 6);
});

test("rechecks an earlier healthy service while the other services progress", async () => {
  let iteration = 0;
  await assert.rejects(
    waitRollouts({
      read: async (kind, name) => {
        if (kind === "deployment") return deployment;
        const rollout = ready();
        rollout.metadata.name = name;
        if (!iteration && name === "proxy")
          rollout.status.phase = "Progressing";
        if (iteration && name === "api") rollout.status.abort = true;
        return rollout;
      },
      wait: async () => {
        iteration++;
      },
    }),
    /api: rollout aborted/,
  );
});
