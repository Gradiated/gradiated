import assert from "node:assert/strict";
import { test } from "node:test";
import { stageCanary, plan } from "./stage-glm-sglang-canary.mjs";

const source = "a".repeat(40);
const digest = "b".repeat(64);
const input = () => ({
  models: { [plan.primary]: { runtime: "old", replicas: 10 } },
  runtimes: { old: { model_id: plan.model } },
  pins: { hostBundle: { baseId: "ubuntu24-cuda13-amd64-v3" } },
  release: {
    bundle: plan.bundle,
    source,
    sha256: digest,
    baseId: "ubuntu24-cuda13-amd64-v3",
    baseImage: `registry/base@sha256:${"c".repeat(64)}`,
    url: `s3::https://gradiated-prod-model-artifacts-873716897517.s3.us-east-1.amazonaws.com/bundles/sha256/${digest}.tar.gz`,
  },
  expectedSource: source,
});

test("stages only one two-GPU canary and preserves the primary", () => {
  const args = input();
  const before = structuredClone(args);
  const result = stageCanary(args);
  const candidate = result.models[plan.name];
  assert.deepEqual(args, before);
  assert.deepEqual(result.models[plan.primary], before.models[plan.primary]);
  assert.equal(candidate.canary_for, plan.primary);
  assert.equal(candidate.replicas, 1);
  assert.equal(candidate.max_surge, 0);
  assert.equal(candidate.max_unavailable, 1);
  assert.equal(candidate.autoscaling.max_replicas, 1);
  assert.equal(
    candidate.node_selector["gradiated.com/instance-id"],
    plan.instance_id,
  );
  const runtime = result.runtimes[digest];
  assert.equal(runtime.gpus, 2);
  assert.equal((candidate.replicas + candidate.max_surge) * runtime.gpus, 2);
  assert.equal(runtime.release.model_revision, plan.checkpoint_revision);
  assert.equal(runtime.release.protocol, undefined);
  assert.equal(runtime.warmup, true);
  assert.deepEqual(stageCanary({ ...args, ...result }), result);
});

test("rejects unrelated, stale, unbound or incompatible release records", () => {
  for (const change of [
    { source: "d".repeat(40) },
    { bundle: "glm-5-3-flash" },
    { sha256: "latest" },
    { baseId: "wrong-base" },
    { baseImage: "registry/base:latest" },
    { url: "https://untrusted.example/archive.tar.gz" },
  ]) {
    const args = input();
    assert.throws(() =>
      stageCanary({ ...args, release: { ...args.release, ...change } }),
    );
  }
});

test("preserves intentional canary rollbacks and immutable runtime definitions", () => {
  const args = input();
  const result = stageCanary(args);
  assert.throws(
    () =>
      stageCanary({
        ...args,
        ...result,
        models: {
          ...result.models,
          [plan.name]: { ...result.models[plan.name], runtime: "rollback" },
        },
      }),
    /explicitly/,
  );
  assert.throws(
    () =>
      stageCanary({
        ...args,
        ...result,
        runtimes: {
          ...result.runtimes,
          [digest]: { ...result.runtimes[digest], gpus: 8 },
        },
      }),
    /immutable/,
  );
  assert.throws(
    () =>
      stageCanary({ ...args, runtimes: { old: { model_id: "other/model" } } }),
    /exact canary model/,
  );
});

test("rejects a second canary consuming the initial two-GPU budget", () => {
  const args = input();
  args.models.other = { canary_for: plan.primary, runtime: "old", replicas: 1 };
  assert.throws(() => stageCanary(args), /different canary/);
});

test("isolates private runtime identity until explicit guarded promotion", () => {
  const args = input();
  const isolated = stageCanary(args);
  assert.equal(isolated.runtimes[digest].model_id, plan.runtime_model);
  assert.notEqual(plan.runtime_model, plan.model);
  assert.equal(isolated.models[plan.name].serving_model_id, plan.model);
  assert.equal(isolated.models[plan.name].serving_mode, "qualification");
  assert.throws(
    () => stageCanary({ ...args, promote: true }),
    /previously isolated/,
  );
  assert.throws(
    () =>
      stageCanary({
        ...args,
        ...isolated,
        runtimes: args.runtimes,
        promote: true,
      }),
    /existing immutable/,
  );
  const promoted = stageCanary({ ...args, ...isolated, promote: true });
  assert.equal(promoted.models[plan.name].serving_mode, "production");
  assert.deepEqual(promoted.runtimes, isolated.runtimes);
  assert.deepEqual(promoted.models[plan.primary], args.models[plan.primary]);
  assert.deepEqual(
    stageCanary({ ...args, ...promoted, promote: true }),
    promoted,
  );
  assert.throws(() => stageCanary({ ...args, ...promoted }), /explicitly/);
  for (const change of [
    { runtime: "rollback" },
    { replicas: 2 },
    { serving_model_id: "other/model" },
  ]) {
    assert.throws(
      () =>
        stageCanary({
          ...args,
          ...isolated,
          promote: true,
          models: {
            ...isolated.models,
            [plan.name]: { ...isolated.models[plan.name], ...change },
          },
        }),
      /previously isolated/,
    );
  }
});
