import { test } from "node:test";
import assert from "node:assert/strict";
import { modelReplicaRules } from "./model-replica-rules.mjs";
const rollout = (model, count) => ({
  kind: "Rollout",
  metadata: { name: "test" },
  spec: {
    replicas: count,
    template: {
      metadata: { annotations: { "gradiated.com/model-id": model } },
    },
  },
});
test("desired counts come from Kubernetes Rollouts, including scale to zero", () => {
  const result = modelReplicaRules([
    rollout("a/b", 2),
    rollout("a/c", 0),
    { kind: "Deployment" },
  ]);
  assert.deepEqual(
    result.spec.groups[0].rules
      .filter((r) => r.record === "gradiated_model_desired_replicas")
      .map((r) => r.expr),
    ["vector(2)", "vector(0)"],
  );
});
test("invalid or duplicate desired state cannot erase or overwrite monitoring", () => {
  for (const input of [
    [],
    [rollout("a/b", -1)],
    [rollout("a/b", 1), rollout("a/b", 2)],
    [rollout(undefined, 1)],
  ])
    assert.throws(() => modelReplicaRules(input));
});

test("autoscaled model monitoring follows the HPA instead of the bootstrap count", () => {
  const scaler = {
    kind: "ScaledObject",
    metadata: { name: "test", namespace: "gpu-inference" },
    spec: { scaleTargetRef: { kind: "Rollout", name: "test" } },
  };
  const result = modelReplicaRules([rollout("a/b", 1), scaler]);
  assert.equal(
    result.spec.groups[0].rules.find(
      (r) => r.record === "gradiated_model_minimum_replicas",
    ).expr,
    "vector(1)",
  );
  assert.equal(
    result.spec.groups[0].rules[0].expr,
    'max(kube_horizontalpodautoscaler_status_desired_replicas{namespace="gpu-inference",horizontalpodautoscaler="keda-hpa-test"}) or vector(1)',
  );
});

test("paused KEDA replicas override bootstrap and HPA counts", () => {
  const scaler = {
    kind: "ScaledObject",
    metadata: {
      name: "test",
      namespace: "gpu-inference",
      annotations: { "autoscaling.keda.sh/paused-replicas": "0" },
    },
    spec: { scaleTargetRef: { kind: "Rollout", name: "test" } },
  };
  const rules = modelReplicaRules([rollout("a/b", 2), scaler]).spec.groups[0]
    .rules;
  assert.deepEqual(
    rules.map((rule) => rule.expr),
    ["vector(0)", "vector(0)"],
  );
  for (const paused of ["-1", "1.5", "NaN", "", 0, "9007199254740992"]) {
    scaler.metadata.annotations["autoscaling.keda.sh/paused-replicas"] = paused;
    assert.throws(
      () => modelReplicaRules([rollout("a/b", 2), scaler]),
      /Invalid paused/,
    );
  }
});

test("an explicit same-model canary keeps separate replica targets", () => {
  const primary = rollout("a/b", 10);
  primary.metadata.name = "primary";
  const candidate = rollout("a/b", 1);
  candidate.metadata.name = "candidate";
  candidate.spec.template.metadata.annotations["gradiated.com/canary-of"] =
    "primary";
  const rules = modelReplicaRules([candidate, primary]).spec.groups[0].rules;
  assert.deepEqual(
    rules
      .filter((rule) => rule.record === "gradiated_model_desired_replicas")
      .map((rule) => [rule.labels.model, rule.labels.rollout, rule.expr]),
    [
      ["a/b", "candidate", "vector(1)"],
      ["a/b", "primary", "vector(10)"],
    ],
  );
});

test("canary warmup does not raise the established minimum serving floor", () => {
  const primary = rollout("a/b", 10);
  primary.metadata.name = "primary";
  const candidate = rollout("a/b", 1);
  candidate.metadata.name = "candidate";
  candidate.spec.template.metadata.annotations["gradiated.com/canary-of"] =
    "primary";
  const rules = modelReplicaRules([primary, candidate]).spec.groups[0].rules;
  assert.deepEqual(
    rules
      .filter((rule) => rule.record === "gradiated_model_minimum_replicas")
      .map((rule) => [rule.labels.rollout, rule.expr]),
    [
      ["primary", "vector(10)"],
      ["candidate", "vector(0)"],
    ],
  );
  const scaler = {
    kind: "ScaledObject",
    metadata: {
      name: "candidate",
      namespace: "gpu-inference",
      annotations: { "autoscaling.keda.sh/paused-replicas": "1" },
    },
    spec: { scaleTargetRef: { kind: "Rollout", name: "candidate" } },
  };
  const pausedRules = modelReplicaRules([primary, candidate, scaler]).spec
    .groups[0].rules;
  assert.equal(
    pausedRules.find(
      (rule) =>
        rule.record === "gradiated_model_desired_replicas" &&
        rule.labels.rollout === "candidate",
    ).expr,
    "vector(1)",
  );
});

test("a production canary inherits the serving floor when its primary is retired", () => {
  const primary = rollout("a/b", 2);
  primary.metadata.name = "primary";
  const candidate = rollout("a/b", 5);
  candidate.metadata.name = "candidate";
  const annotations = candidate.spec.template.metadata.annotations;
  annotations["gradiated.com/canary-of"] = "primary";
  annotations["gradiated.com/serving-mode"] = "production";
  const scaler = {
    kind: "ScaledObject",
    metadata: {
      name: "primary",
      namespace: "gpu-inference",
      annotations: { "autoscaling.keda.sh/paused-replicas": "0" },
    },
    spec: { scaleTargetRef: { kind: "Rollout", name: "primary" } },
  };
  const minima = (resources) =>
    modelReplicaRules(resources)
      .spec.groups[0].rules.filter(
        (rule) => rule.record === "gradiated_model_minimum_replicas",
      )
      .map((rule) => [rule.labels.rollout, rule.expr]);
  for (const resources of [
    [primary, candidate, scaler],
    [candidate, scaler, primary],
  ]) {
    assert.deepEqual(
      new Map(minima(resources)),
      new Map([
        ["primary", "vector(0)"],
        ["candidate", "vector(5)"],
      ]),
    );
  }
  // A zero Rollout count without KEDA is also a retired primary.
  assert.deepEqual(
    minima([{ ...primary, spec: { ...primary.spec, replicas: 0 } }, candidate]),
    [
      ["primary", "vector(0)"],
      ["candidate", "vector(5)"],
    ],
  );
  annotations["gradiated.com/serving-mode"] = "qualification";
  assert.deepEqual(minima([primary, candidate, scaler]), [
    ["primary", "vector(0)"],
    ["candidate", "vector(0)"],
  ]);
  annotations["gradiated.com/serving-mode"] = "production";
  delete scaler.metadata.annotations["autoscaling.keda.sh/paused-replicas"];
  assert.deepEqual(minima([primary, candidate, scaler]), [
    ["primary", "vector(2)"],
    ["candidate", "vector(0)"],
  ]);
});

test("split replacement pools preserve their aggregate PDB floor during sixth warmup", () => {
  const primary = rollout("a/b", 0);
  primary.metadata.name = "primary";
  const main = rollout("a/b", 5);
  main.metadata.name = "main";
  main.spec.template.metadata.annotations["gradiated.com/canary-of"] =
    "primary";
  const sixth = rollout("a/b", 1);
  sixth.metadata.name = "sixth";
  sixth.spec.template.metadata.annotations["gradiated.com/canary-of"] =
    "primary";
  const budgets = [
    {
      kind: "PodDisruptionBudget",
      metadata: { name: "main" },
      spec: { minAvailable: 4 },
    },
    {
      kind: "PodDisruptionBudget",
      metadata: { name: "sixth" },
      spec: { minAvailable: 1 },
    },
  ];
  const minima = (items) =>
    new Map(
      modelReplicaRules(items)
        .spec.groups[0].rules.filter(
          (rule) => rule.record === "gradiated_model_minimum_replicas",
        )
        .map((rule) => [rule.labels.rollout, rule.expr]),
    );
  for (const items of [
    [primary, main, sixth, ...budgets],
    [...budgets, sixth, main, primary],
  ])
    assert.deepEqual(
      minima(items),
      new Map([
        ["primary", "vector(0)"],
        ["main", "vector(4)"],
        ["sixth", "vector(1)"],
      ]),
    );
  sixth.spec.template.metadata.annotations["gradiated.com/serving-mode"] =
    "qualification";
  assert.deepEqual(
    minima([primary, main, sixth, ...budgets]),
    new Map([
      ["primary", "vector(0)"],
      ["main", "vector(5)"],
      ["sixth", "vector(0)"],
    ]),
  );
  sixth.spec.template.metadata.annotations["gradiated.com/serving-mode"] =
    "production";
  primary.spec.replicas = 2;
  assert.deepEqual(
    minima([primary, main, sixth, ...budgets]),
    new Map([
      ["primary", "vector(2)"],
      ["main", "vector(0)"],
      ["sixth", "vector(0)"],
    ]),
  );
  primary.spec.replicas = 0;
  assert.equal(minima([primary, main, sixth]).get("main"), "vector(5)");
  for (const invalid of [-1, 2, "50%", null]) {
    budgets[1].spec.minAvailable = invalid;
    assert.throws(
      () => minima([primary, main, sixth, ...budgets]),
      /disruption floor/,
    );
  }
});

test("isolated qualification does not request production serving capacity", () => {
  const primary = rollout("a/b", 10);
  primary.metadata.name = "primary";
  const candidate = rollout("private/candidate", 1);
  candidate.metadata.name = "candidate";
  const annotations = candidate.spec.template.metadata.annotations;
  annotations["gradiated.com/canary-of"] = "primary";
  annotations["gradiated.com/serving-model-id"] = "a/b";
  annotations["gradiated.com/serving-mode"] = "qualification";
  const desired = () =>
    modelReplicaRules([primary, candidate])
      .spec.groups[0].rules.filter(
        (rule) => rule.record === "gradiated_model_desired_replicas",
      )
      .map((rule) => [rule.labels.model, rule.expr]);
  assert.deepEqual(desired(), [
    ["a/b", "vector(10)"],
    ["a/b", "vector(0)"],
  ]);
  annotations["gradiated.com/serving-mode"] = "production";
  assert.deepEqual(desired(), [
    ["a/b", "vector(10)"],
    ["a/b", "vector(1)"],
  ]);
  annotations["gradiated.com/serving-mode"] = "unknown";
  assert.throws(desired, /qualification mode/);
  delete annotations["gradiated.com/serving-mode"];
  assert.throws(desired, /explicit mode/);
  annotations["gradiated.com/serving-model-id"] = "";
  assert.throws(desired, /model identity/);
});

test("canary annotations cannot bypass model identity validation", () => {
  const primary = rollout("a/b", 10);
  primary.metadata.name = "primary";
  for (const [model, parent] of [
    ["a/b", "missing"],
    ["a/c", "primary"],
    ["a/b", "candidate"],
  ]) {
    const candidate = rollout(model, 1);
    candidate.metadata.name = "candidate";
    candidate.spec.template.metadata.annotations["gradiated.com/canary-of"] =
      parent;
    assert.throws(() => modelReplicaRules([primary, candidate]), /canary/i);
  }
});
