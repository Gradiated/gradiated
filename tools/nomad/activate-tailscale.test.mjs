import assert from "node:assert/strict";
import test from "node:test";
import {
  qualificationJob,
  inferenceReady,
  waitForQualification,
} from "./activate-tailscale.mjs";
const instance = "00000000-0000-4000-8000-000000000001";
const image =
  "873716897517.dkr.ecr.us-east-1.amazonaws.com/gradiated/prod/product@sha256:" +
  "a".repeat(64);

test("qualification defaults to no mutation and uses secret references rather than secret values", () => {
  const job = qualificationJob(instance, image);
  const container = job.spec.template.spec.containers[0];
  assert.deepEqual(container.args, ["--instance-id", instance]);
  assert.equal(job.spec.activeDeadlineSeconds, 300);
  assert.equal(job.spec.template.spec.automountServiceAccountToken, false);
  assert(
    container.env.every((e) => e.valueFrom.secretKeyRef && !("value" in e)),
  );
  assert(!JSON.stringify(job).includes("tskey-"));
  assert.deepEqual(
    qualificationJob(instance, image, true).spec.template.spec.containers[0]
      .args,
    ["--instance-id", instance, "--apply"],
  );
});

test("refuses invalid instance IDs and mutable image references", () => {
  assert.throws(() => qualificationJob("invalid", image));
  assert.throws(() => qualificationJob(instance, "example/product:latest"));
  assert.throws(() =>
    qualificationJob(instance, "untrusted/product@sha256:" + "a".repeat(64)),
  );
});

const readyPod = (name, nodeName = name) => ({
  metadata: { name },
  spec: { nodeName },
  status: { conditions: [{ type: "Ready", status: "True" }] },
});
const readyRelay = () => ({
  metadata: { generation: 2 },
  spec: { replicas: 3 },
  status: {
    conditions: [
      { type: "PeerRelayReady", status: "True", observedGeneration: 2 },
    ],
    endpoints: [
      { replica: 0, address: "203.0.113.1", port: 41641 },
      { replica: 1, address: "203.0.113.2", port: 41641 },
      { replica: 2, address: "203.0.113.3", port: 41641 },
    ],
  },
});

test("requires distinct ready relay replicas and advertised endpoints, not desired count", () => {
  const relay = readyRelay();
  const pods = {
    items: [readyPod("relay-0"), readyPod("relay-1"), readyPod("relay-2")],
  };
  assert(
    !inferenceReady({ ...relay, spec: { replicas: 2 } }, "peerrelay", pods),
  );
  assert(
    !inferenceReady(relay, "peerrelay", { items: pods.items.slice(0, 2) }),
  );
  assert(
    !inferenceReady(relay, "peerrelay", {
      items: [
        readyPod("relay-0", "same-node"),
        readyPod("relay-1", "same-node"),
        readyPod("relay-2"),
      ],
    }),
  );
  assert(inferenceReady(relay, "peerrelay", pods));
  assert(!inferenceReady(relay, "peerrelay", { items: [readyPod("relay-0")] }));
  assert(
    !inferenceReady(relay, "peerrelay", {
      items: [readyPod("relay-0"), readyPod("relay-0"), readyPod("relay-2")],
    }),
  );
  assert(
    !inferenceReady(relay, "peerrelay", {
      items: [
        readyPod("relay-0"),
        readyPod("relay-2"),
        {
          ...readyPod("relay-1"),
          metadata: { name: "relay-1", deletionTimestamp: "2026-10-12" },
        },
      ],
    }),
  );
  relay.status.endpoints[1].replica = 0;
  assert(!inferenceReady(relay, "peerrelay", pods));
  relay.status.endpoints[1].replica = 1;
  relay.status.endpoints[1].port = 0;
  assert(!inferenceReady(relay, "peerrelay", pods));
});

test("requires three ready egress pods on distinct nodes", () => {
  const proxy = readyRelay();
  proxy.status.conditions[0].type = "ProxyGroupReady";
  assert(
    inferenceReady(proxy, "proxygroup", {
      items: [readyPod("egress-0"), readyPod("egress-1"), readyPod("egress-2")],
    }),
  );
  assert(
    !inferenceReady(proxy, "proxygroup", { items: [readyPod("egress-0")] }),
  );
});

test("waits until the qualification Job completes and rejects failed Jobs", async () => {
  let reads = 0;
  await waitForQualification(
    async () => ({
      status: {
        conditions: ++reads === 1 ? [] : [{ type: "Complete", status: "True" }],
      },
    }),
    { pause: async () => {} },
  );
  assert.equal(reads, 2);
  for (const type of ["Failed", "FailureTarget"]) {
    await assert.rejects(
      waitForQualification(async () => ({
        status: { conditions: [{ type, status: "True" }] },
      })),
      /Job failed/,
    );
  }
});

test("bounds waiting for a pending or unschedulable Job", async () => {
  let time = 0;
  await assert.rejects(
    waitForQualification(async () => ({}), {
      now: () => time,
      pause: async (ms) => {
        time += ms;
      },
      timeoutMs: 5,
    }),
    /timed out/,
  );
});
