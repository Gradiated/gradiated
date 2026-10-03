import assert from "node:assert/strict";
import { test } from "node:test";
import { verificationInfrastructureReady } from "./verification-infrastructure.mjs";

const deployments = () =>
  ["gateway", "worker"].map((name) => ({
    kind: "Deployment",
    metadata: { name, namespace: "gradiated", generation: 3 },
    spec: {
      replicas: 3,
      template: {
        spec: {
          containers: [
            {
              name,
              image: `${name}@sha256:current`,
              env: (name === "gateway"
                ? ["GATEWAY_VERIFICATION_WORKSPACE_ID"]
                : [
                    "MODEL_VERIFICATION_WORKSPACE_ID",
                    "MODEL_VERIFICATION_USER_ID",
                  ]
              ).map((name) => ({ name, value: "configured" })),
            },
          ],
        },
      },
    },
    status: {
      observedGeneration: 3,
      replicas: 3,
      updatedReplicas: 3,
      readyReplicas: 3,
      availableReplicas: 3,
    },
  }));

test("requires the Git-defined verification config fully rolled out", () => {
  assert.ok(verificationInfrastructureReady(deployments(), deployments()));
  for (const change of [
    (item) => (item.spec.template.spec.containers[0].image = "stale-worker"),
    (item) => (item.spec.template.spec.containers[0].env = []),
    (item) =>
      (item.spec.template.spec.containers[0].env[0].value = "old-workspace"),
    (item) => (item.status.observedGeneration = 2),
    (item) => (item.status.updatedReplicas = 2),
    (item) => (item.status.readyReplicas = 2),
    (item) => (item.status.availableReplicas = 2),
    (item) => (item.status.replicas = 4),
  ]) {
    const live = deployments();
    change(live[0]);
    assert.equal(verificationInfrastructureReady(deployments(), live), false);
  }
  assert.equal(verificationInfrastructureReady(deployments(), []), false);
});
