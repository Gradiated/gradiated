import assert from "node:assert/strict";
import test from "node:test";
import { checkTrainingReadiness } from "./training-readiness.mjs";

const image = "product@sha256:release";
const fixture = () => ({
  apiConfig: { data: {} },
  apiDeployment: { spec: { template: { spec: { containers: [{}] } } } },
  workerConfig: { data: { TRAINING_EXECUTOR: "qwen-sft" } },
  workerDeployment: {
    metadata: { generation: 2 },
    spec: { replicas: 1, template: { spec: { containers: [{}] } } },
    status: {
      observedGeneration: 2,
      updatedReplicas: 1,
      availableReplicas: 1,
      readyReplicas: 1,
    },
  },
  pods: {
    items: [
      {
        metadata: {},
        spec: { containers: [{ name: "temporal-worker", image }] },
        status: {
          containerStatuses: [{ name: "temporal-worker", ready: true }],
          conditions: [{ type: "Ready", status: "True" }],
        },
      },
    ],
  },
  productImage: image,
});

test("disabled admission and zero replicas are explicitly disabled", () => {
  const state = fixture();
  state.workerDeployment.spec.replicas = 0;
  assert.equal(checkTrainingReadiness(state), "disabled");
  assert.throws(() => checkTrainingReadiness({ ...state, requireReady: true }));
  state.apiConfig.data.TRAINING_EXECUTOR = "qwen-sft";
  assert.throws(() => checkTrainingReadiness(state));
});

test("ready real workers qualify before API admission", () => {
  const state = fixture();
  assert.equal(checkTrainingReadiness(state), "ready");
  state.apiConfig.data.TRAINING_EXECUTOR = "qwen-sft";
  assert.equal(checkTrainingReadiness(state), "ready");
});

test("mock, missing executor and implicit environment overrides fail closed", () => {
  for (const mutate of [
    (s) => {
      s.apiConfig.data.TRAINING_EXECUTOR = "mock";
    },
    (s) => {
      s.workerConfig.data.TRAINING_EXECUTOR = "mock";
    },
    (s) => {
      delete s.workerConfig.data.TRAINING_EXECUTOR;
    },
    (s) => {
      s.apiDeployment.spec.template.spec.containers[0].env = [
        { name: "TRAINING_EXECUTOR", valueFrom: {} },
      ];
    },
  ]) {
    const state = fixture();
    mutate(state);
    assert.throws(() => checkTrainingReadiness(state));
  }
});

test("stale rollouts, images and terminating pods cannot qualify", () => {
  for (const mutate of [
    (s) => {
      s.workerDeployment.status.observedGeneration = 1;
    },
    (s) => {
      s.workerDeployment.status.updatedReplicas = 0;
    },
    (s) => {
      s.workerDeployment.status.availableReplicas = 0;
    },
    (s) => {
      s.workerDeployment.status.readyReplicas = 0;
    },
    (s) => {
      s.pods.items[0].spec.containers[0].image = "old";
    },
    (s) => {
      s.pods.items[0].metadata.deletionTimestamp = "now";
    },
    (s) => {
      s.pods.items[0].status.containerStatuses[0].ready = false;
    },
    (s) => {
      s.pods.items[0].status.conditions = [];
    },
  ]) {
    const state = fixture();
    mutate(state);
    assert.throws(() => checkTrainingReadiness(state));
  }
});
