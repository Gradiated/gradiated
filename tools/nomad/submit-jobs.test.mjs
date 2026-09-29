import test from "node:test";
import assert from "node:assert/strict";
import { deployJobs, submitJob } from "./submit-jobs.mjs";

const job = { ID: "model" };
const signal = () => new AbortController().signal;

test("a failed model does not abort supervision of another model's rollout", async () => {
  let finishHealthy;
  let settled = false;
  const healthy = new Promise((resolve) => {
    finishHealthy = resolve;
  });
  const result = deployJobs(
    [{ ID: "failed" }, { ID: "healthy" }],
    async ({ ID }) => {
      if (ID === "failed") throw new Error("canary failed");
      await healthy;
    },
  );
  const checked = assert.rejects(result, /failed: canary failed/);
  void result.catch(() => {
    settled = true;
  });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(settled, false);
  finishHealthy();
  await checked;
});

test("independent deployment failures are all reported", async () => {
  await assert.rejects(
    deployJobs([{ ID: "a" }, { ID: "b" }], async ({ ID }) => {
      throw new Error(`${ID} failed`);
    }),
    { message: "a: a failed\nb: b failed" },
  );
  await deployJobs([{ ID: "healthy" }], async () => {});
});

test("an unchanged reverted job does not follow the failed deployment it replaced", async () => {
  const result = await submitJob(job, {
    signal: signal(),
    get: async () => [
      { ID: "failed-canary", CreateIndex: 2, Status: "failed" },
    ],
    post: async (path) => {
      assert.equal(path, "/v1/job/model/plan");
      return { Diff: { Type: "None" }, JobModifyIndex: 10 };
    },
  });
  assert.deepEqual(result, { deployment: undefined });
});

test("an unchanged job preserves its active canaries without registration", async () => {
  const calls = [];
  const result = await submitJob(job, {
    signal: signal(),
    get: async () => [{ ID: "existing", CreateIndex: 2, Status: "running" }],
    post: async (path) => {
      calls.push(path);
      assert.equal(path, "/v1/job/model/plan");
      return { Diff: { Type: "None" }, JobModifyIndex: 10 };
    },
  });
  assert.deepEqual(result, { deployment: "existing" });
  assert.equal(calls.length, 1);
});

test("a changed release waits for promotion and draining before reclaiming GPUs", async () => {
  let phase = 0;
  const registrations = [];
  const result = await submitJob(job, {
    signal: signal(),
    pause: async () => {
      phase++;
    },
    get: async (path) =>
      path.endsWith("deployments")
        ? [
            {
              ID: "old",
              CreateIndex: 2,
              Status: phase === 0 ? "running" : "successful",
            },
          ]
        : [
            {
              JobID: "another-model",
              DesiredStatus: "stop",
              ClientStatus: phase === 1 ? "running" : "complete",
            },
          ],
    post: async (path, body) => {
      if (path.endsWith("plan"))
        return { Diff: { Type: "Edited" }, JobModifyIndex: phase + 10 };
      assert.equal(phase, 2);
      registrations.push(body);
      return { EvalID: "new-evaluation" };
    },
  });
  assert.deepEqual(result, { evaluation: "new-evaluation", previous: "old" });
  assert.deepEqual(registrations, [
    { Job: job, EnforceIndex: true, JobModifyIndex: 12 },
  ]);
});

test("another job can submit while one waits for its earlier rollout", async () => {
  const controller = new AbortController();
  let releaseWait;
  const pause = () =>
    new Promise((resolve) => {
      releaseWait = resolve;
    });
  const stalled = submitJob(job, {
    signal: controller.signal,
    pause,
    post: async () => ({ Diff: { Type: "Edited" }, JobModifyIndex: 10 }),
    get: async () => [{ ID: "old", Status: "running" }],
  });
  await new Promise((resolve) => setImmediate(resolve));
  const ready = await submitJob(
    { ID: "other" },
    {
      signal: signal(),
      get: async () => [],
      post: async (path) =>
        path.endsWith("plan")
          ? { Diff: { Type: "Added" }, JobModifyIndex: 0 }
          : { EvalID: "other-evaluation" },
    },
  );
  assert.equal(ready.evaluation, "other-evaluation");
  controller.abort();
  releaseWait();
  await assert.rejects(stalled, /deadline/);
});

test("a missing structured diff cannot be mistaken for no change", async () => {
  await assert.rejects(
    submitJob(job, {
      signal: signal(),
      post: async () => ({ JobModifyIndex: 0 }),
    }),
    /Unrecognized plan/,
  );
});

test("a failed previous deployment permits a replacement once drains finish", async () => {
  const result = await submitJob(job, {
    signal: signal(),
    get: async (path) =>
      path.endsWith("deployments") ? [{ ID: "bad", Status: "failed" }] : [],
    post: async (path) =>
      path.endsWith("plan")
        ? { Diff: { Type: "Edited" }, JobModifyIndex: 12 }
        : { EvalID: "fixed" },
  });
  assert.equal(result.evaluation, "fixed");
});

test("an unreachable stopped allocation cannot block releases on healthy hosts", async () => {
  const result = await submitJob(job, {
    signal: signal(),
    pause: async () => {
      assert.fail("An unknown allocation cannot confirm its drain");
    },
    get: async (path) =>
      path.endsWith("deployments")
        ? [{ ID: "previous", Status: "successful" }]
        : [
            {
              JobID: "another-model",
              DesiredStatus: "stop",
              ClientStatus: "unknown",
            },
          ],
    post: async (path) =>
      path.endsWith("plan")
        ? { Diff: { Type: "Edited" }, JobModifyIndex: 12 }
        : { EvalID: "replacement" },
  });

  assert.equal(result.evaluation, "replacement");
});
