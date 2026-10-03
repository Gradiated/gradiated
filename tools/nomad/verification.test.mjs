import assert from "node:assert/strict";
import { test } from "node:test";
import { EventEmitter } from "node:events";
import { createVerificationGate, verifyInProduction } from "./verification.mjs";

const interruptedExecutor = (codes) => {
  const inputs = [];
  return {
    inputs,
    spawnProcess: () => {
      const child = new EventEmitter();
      child.stdin = new EventEmitter();
      child.stdin.end = (input) => {
        inputs.push(JSON.parse(input));
        queueMicrotask(() => child.emit("close", codes.shift()));
      };
      return child;
    },
    pause: async () => {},
  };
};

test("worker termination repeats the complete SDK check before succeeding", async () => {
  const executor = interruptedExecutor([137, 143, 0]);
  const input = { stage: "canary", deploymentIds: ["new-allocation"] };
  await verifyInProduction(input, undefined, executor);
  assert.deepEqual(executor.inputs, [input, input, input]);
});

test("SDK assertion failures are not retried", async () => {
  const executor = interruptedExecutor([1, 0]);
  await assert.rejects(
    verifyInProduction({}, undefined, executor),
    /exited with 1$/,
  );
  assert.equal(executor.inputs.length, 1);
});

test("repeated worker termination fails after three attempts", async () => {
  const executor = interruptedExecutor([137, 137, 137, 0]);
  await assert.rejects(
    verifyInProduction({}, undefined, executor),
    /exited with 137$/,
  );
  assert.equal(executor.inputs.length, 3);
});

test("cancellation between attempts prevents another verification", async () => {
  const executor = interruptedExecutor([143, 0]);
  const controller = new AbortController();
  executor.pause = async () => controller.abort();
  await assert.rejects(verifyInProduction({}, controller.signal, executor), {
    name: "AbortError",
  });
  assert.equal(executor.inputs.length, 1);
});

const fixture = async (overrides = {}) => {
  const controller = new AbortController();
  const state = {
    allocations: ["one", "two"].map((ID) => ({
      ID,
      JobVersion: 2,
      TaskGroup: "replicas",
      DesiredStatus: "run",
      ClientStatus: "running",
    })),
    time: 110_000,
    minimum: 0,
    checks: { runtime: { Status: "success", Timestamp: 100 } },
    posts: [],
    verified: [],
    ...overrides,
  };
  const options = {
    signal: controller.signal,
    now: () => state.time,
    get: async (path) => {
      if (path.endsWith("/versions"))
        return {
          Versions: [
            {
              Version: 2,
              Meta: {
                gradiated_sdk_verification: "true",
                gradiated_model_id: "model",
                gradiated_release: '{"runtime_revision":"v2"}',
                ...state.meta,
              },
              TaskGroups: [
                {
                  Name: "replicas",
                  Count: state.count ?? 2,
                  Update: {
                    HealthCheck: "manual",
                    MinHealthyTime: state.minimum,
                    AutoPromote: true,
                    AutoRevert: true,
                    Canary: 2,
                    ...state.update,
                  },
                },
              ],
            },
          ],
        };
      if (path.endsWith("/checks")) return state.checks;
      if (path === "/v1/deployment/allocations/rollout")
        return structuredClone(state.allocations);
      if (path === "/v1/deployment/rollout")
        return {
          TaskGroups: { replicas: { DesiredCanaries: 1, Promoted: false } },
        };
      throw new Error(`Unexpected ${path}`);
    },
    post: async (path, body) => {
      state.posts.push({ path, body });
      if (path.includes("allocation-health"))
        for (const allocation of state.allocations)
          if (body.HealthyAllocationIDs.includes(allocation.ID))
            allocation.DeploymentStatus = { Healthy: true };
    },
    verify: async (input) => {
      state.verified.push(input);
      await state.onVerify?.(input, controller);
    },
  };
  const gate = await createVerificationGate(
    { ID: "rollout", JobID: "model", JobVersion: 2 },
    options,
  );
  return { state, gate, controller };
};

test("the remaining legacy singleton verifies its slot while migrated peers serve", async () => {
  const { gate, state } = await fixture({
    count: 1,
    allocations: [
      {
        ID: "one",
        JobVersion: 2,
        TaskGroup: "replicas",
        DesiredStatus: "run",
        ClientStatus: "running",
      },
    ],
    update: { Canary: 1 },
  });
  await gate.qualify();
  await gate.finish();
  assert.ok(state.verified.every((input) => input.replicaRollout === true));
});

test("singleton promotion waits for the serving handoff after SDK qualification", async () => {
  const events = [];
  const { gate, state } = await fixture({
    count: 1,
    allocations: [
      {
        ID: "one",
        JobVersion: 2,
        TaskGroup: "replicas",
        DesiredStatus: "run",
        ClientStatus: "running",
      },
    ],
    meta: { gradiated_replica_parent: "model", gradiated_replica_slot: "0" },
    update: { Canary: 1, AutoPromote: false },
    onVerify: async (input) => events.push(input.stage),
  });
  await gate.qualify();
  assert.deepEqual(events, ["canary", "serving"]);
  assert.deepEqual(
    state.posts.map((post) => post.path),
    [
      "/v1/deployment/allocation-health/rollout",
      "/v1/deployment/promote/rollout",
    ],
  );
  assert.ok(state.verified.every((input) => input.replicaRollout === true));
});

test("failed singleton serving handoff fails before promotion", async () => {
  const { gate, state } = await fixture({
    count: 1,
    allocations: [
      {
        ID: "one",
        JobVersion: 2,
        TaskGroup: "replicas",
        DesiredStatus: "run",
        ClientStatus: "running",
      },
    ],
    meta: { gradiated_replica_parent: "model", gradiated_replica_slot: "0" },
    update: { Canary: 1, AutoPromote: false },
    onVerify: async (input) => {
      if (input.stage === "serving") throw new Error("handoff failed");
    },
  });
  await assert.rejects(gate.qualify(), /handoff failed/);
  assert.deepEqual(
    state.posts.map((post) => post.path),
    ["/v1/deployment/allocation-health/rollout", "/v1/deployment/fail/rollout"],
  );
});

test("only SDK-verified allocation identities become manually healthy", async () => {
  const { gate, state } = await fixture();
  await gate.qualify();
  assert.deepEqual(state.verified, [
    {
      modelId: "model",
      runtimeRevision: "v2",
      stage: "canary",
      deploymentIds: ["one", "two"],
    },
  ]);
  assert.deepEqual(state.posts, [
    {
      path: "/v1/deployment/allocation-health/rollout",
      body: { DeploymentID: "rollout", HealthyAllocationIDs: ["one", "two"] },
    },
  ]);
  await gate.finish();
  assert.equal(state.verified[1].stage, "serving");
  assert.deepEqual(state.verified[1].deploymentIds, ["one", "two"]);
});

test("resuming a rollout verifies only allocations still awaiting qualification", async () => {
  const { gate, state } = await fixture();
  state.allocations[0].DeploymentStatus = { Healthy: true };
  await gate.qualify();
  assert.deepEqual(state.verified[0].deploymentIds, ["two"]);
  assert.deepEqual(state.posts[0].body.HealthyAllocationIDs, ["two"]);
});

test("a replacement during verification cannot inherit health", async () => {
  const { gate, state } = await fixture();
  state.onVerify = async () => {
    state.allocations[0].ID = "replacement";
  };
  await gate.qualify();
  assert.deepEqual(state.posts[0].body.HealthyAllocationIDs, ["two"]);
  await gate.qualify();
  assert.ok(
    state.verified.some((item) => item.deploymentIds.includes("replacement")),
  );
});

for (const checks of [
  {},
  { runtime: { Status: "failure", Timestamp: 100 } },
  { runtime: { Status: "success", Timestamp: 1 } },
  { runtime: { Status: "success", Timestamp: 100_000_000_000 } },
]) {
  test(`unready or stale checks never start SDK qualification: ${JSON.stringify(checks)}`, async () => {
    const { gate, state } = await fixture({ checks });
    await gate.qualify();
    assert.equal(state.verified.length, 0);
    assert.equal(state.posts.length, 0);
  });
}

test("incomplete placement waits instead of promoting a subset", async () => {
  const { gate, state } = await fixture();
  state.allocations.pop();
  await gate.qualify();
  assert.equal(state.verified.length, 0);
});

test("a failed pre-promotion SDK check fails the deployment", async () => {
  const { gate, state } = await fixture({
    onVerify: async () => {
      throw new Error("SDK failed");
    },
  });
  await assert.rejects(gate.qualify(), /SDK failed/);
  assert.equal(state.posts[0].path, "/v1/deployment/fail/rollout");
});

test("workflow cancellation leaves the deployment resumable", async () => {
  const { gate, state } = await fixture({
    onVerify: async (_, controller) => {
      controller.abort();
      throw new Error("cancelled");
    },
  });
  await assert.rejects(gate.qualify(), /cancelled/);
  assert.equal(state.posts.length, 0);
});

test("post-promotion failure fails verification without pretending to roll back", async () => {
  const { gate, state } = await fixture({
    onVerify: async () => {
      throw new Error("routing failed");
    },
  });
  await assert.rejects(gate.finish(), /routing failed/);
  assert.equal(state.posts.length, 0);
});

test("requires continuous observed health for the configured minimum", async () => {
  const { gate, state } = await fixture({ minimum: 10_000_000_000 });
  await gate.qualify();
  assert.equal(state.verified.length, 0);
  state.time += 9000;
  state.checks.runtime.Status = "failure";
  await gate.qualify();
  state.checks.runtime.Status = "success";
  await gate.qualify();
  state.time += 9000;
  await gate.qualify();
  assert.equal(state.verified.length, 0);
  state.time += 1000;
  await gate.qualify();
  assert.equal(state.verified.length, 1);
});

test("health lost during SDK verification prevents promotion", async () => {
  const { gate, state } = await fixture();
  state.onVerify = async () => {
    state.checks.runtime.Status = "failure";
  };
  await gate.qualify();
  assert.equal(state.posts.length, 0);
});

for (const options of [
  {
    update: { Canary: 0, MaxParallel: 1, AutoRevert: true, AutoPromote: false },
  },
  { update: { AutoRevert: false } },
  { update: { AutoPromote: false } },
  {
    count: 1,
    update: { Canary: 0, MaxParallel: 1, AutoRevert: true, AutoPromote: false },
  },
  { update: { Canary: 0, MaxParallel: 2, AutoRevert: true } },
  { update: { Canary: 0, MaxParallel: 1, AutoRevert: false } },
  {
    update: { Canary: 0, MaxParallel: 1, AutoRevert: true, AutoPromote: true },
  },
  {
    update: {
      Canary: 0,
      MaxParallel: 1,
      AutoRevert: true,
      HealthCheck: "checks",
    },
  },
  { update: { Canary: 1 } },
]) {
  test(`unsafe partial qualification is rejected: ${JSON.stringify(options)}`, async () => {
    await assert.rejects(fixture(options), /SDK verification requires/);
  });
}
