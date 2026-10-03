import test from "node:test";
import assert from "node:assert/strict";
import { deployJobs, submitJob } from "./submit-jobs.mjs";

const job = { ID: "model" };
const signal = () => new AbortController().signal;

test("a newer recovered system job verifies current allocations instead of its historical failure", async () => {
  const system = {
    ID: "proxy",
    Type: "system",
    Version: 28,
    TaskGroups: [{ Name: "proxy", Count: 1, Update: { MinHealthyTime: 0 } }],
  };
  for (const failure of [
    undefined,
    "node-left",
    "queued",
    "same-version",
    "missing",
    "old-allocation",
    "not-running",
    "unhealthy",
    "stale",
    "empty-checks",
    "transient",
  ]) {
    let inspections = 0;
    let elapsed = 0;
    system.TaskGroups[0].Update.MinHealthyTime =
      failure === "transient" ? 2_000_000_000 : 0;
    const options = {
      signal: signal(),
      pause: async (ms) => {
        elapsed += ms;
      },
      post: async (path) => {
        assert.equal(
          path,
          "/v1/job/proxy/plan",
          "No running proxy should be restarted",
        );
        return { Diff: { Type: "None" }, JobModifyIndex: 42 };
      },
      get: async (path) => {
        if (path === "/v1/job/proxy/deployments")
          return [
            {
              ID: "historical",
              JobVersion: failure === "same-version" ? 28 : 27,
              Status: "failed",
              TaskGroups: { proxy: { DesiredTotal: 2 } },
            },
          ];
        if (path === "/v1/job/proxy") return system;
        if (path === "/v1/job/proxy/summary")
          return {
            Summary: {
              proxy: {
                Running: failure === "node-left" ? 1 : 2,
                Queued: failure === "queued" ? 1 : 0,
                Starting: 0,
                Unknown: 0,
              },
            },
          };
        if (path === "/v1/job/proxy/allocations")
          return Array.from(
            { length: ["missing", "node-left"].includes(failure) ? 1 : 2 },
            (_, i) => ({
              ID: String(i),
              TaskGroup: "proxy",
              DesiredStatus: "run",
              ClientStatus: failure === "not-running" ? "failed" : "running",
              JobVersion: failure === "old-allocation" ? 27 : 28,
            }),
          );
        if (path.endsWith("/checks")) {
          inspections++;
          return failure === "empty-checks"
            ? {}
            : {
                ready: {
                  Status:
                    failure === "unhealthy" ||
                    (failure === "transient" && elapsed === 1000)
                      ? "failure"
                      : "success",
                  Timestamp: Date.now() / 1000 - (failure === "stale" ? 61 : 0),
                },
              };
        }
        throw new Error(path);
      },
    };
    if (failure && failure !== "node-left")
      await assert.rejects(
        submitJob(system, options),
        /failed|missing|not current|unhealthy or stale/,
      );
    else {
      assert.deepEqual(await submitJob(system, options), {
        deployment: undefined,
      });
      assert.equal(
        inspections,
        failure === "node-left" ? 2 : 4,
        "Every current proxy needs fresh checks across the healthy interval",
      );
    }
  }
});

test("models share staging capacity sequentially while infrastructure progresses", async () => {
  const events = [];
  let finishFirst;
  const first = new Promise((resolve) => {
    finishFirst = resolve;
  });
  const result = deployJobs(
    [
      { ID: "first", Meta: { gradiated_model_id: "model-a" } },
      { ID: "second", Meta: { gradiated_model_id: "model-b" } },
      { ID: "host-proxy" },
    ],
    async ({ ID }) => {
      events.push(`start:${ID}`);
      if (ID === "first") await first;
      events.push(`finish:${ID}`);
    },
  );
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(events, [
    "start:first",
    "start:host-proxy",
    "finish:host-proxy",
  ]);
  finishFirst();
  await result;
  assert.deepEqual(events.slice(3), [
    "finish:first",
    "start:second",
    "finish:second",
  ]);
});

test("a failed model releases its turn and later model failures are reported", async () => {
  const events = [];
  await assert.rejects(
    deployJobs(
      ["a", "b"].map((ID) => ({
        ID,
        Meta: { gradiated_model_id: ID },
      })),
      async ({ ID }) => {
        events.push(ID);
        throw new Error(`${ID} rejected`);
      },
    ),
    { message: "a: a rejected\nb: b rejected" },
  );
  assert.deepEqual(events, ["a", "b"]);
});

test("a rejected replica skips its model's remaining replicas while other models continue", async () => {
  const attempted = [];
  await assert.rejects(
    deployJobs(
      [
        { ID: "kev-1", Meta: { gradiated_model_id: "kev" } },
        { ID: "kev-0", Meta: { gradiated_model_id: "kev" } },
        { ID: "glm", Meta: { gradiated_model_id: "glm" } },
      ],
      async ({ ID }) => {
        attempted.push(ID);
        if (ID === "kev-1") throw new Error("SDK rejected");
      },
    ),
    /SDK rejected/,
  );
  assert.deepEqual(attempted, ["kev-1", "glm"]);
});

test("stop-first model updates are rejected before any Nomad request", async () => {
  const unsafe = {
    ...job,
    Meta: { gradiated_sdk_verification: "true" },
    TaskGroups: [
      {
        Count: 2,
        Update: {
          HealthCheck: "manual",
          Canary: 0,
          MaxParallel: 1,
          AutoPromote: false,
          AutoRevert: true,
        },
      },
    ],
  };
  let requests = 0;
  const request = async () => {
    requests++;
  };
  await assert.rejects(
    submitJob(unsafe, {
      signal: signal(),
      get: request,
      post: request,
    }),
    /preserve serving capacity/,
  );
  assert.equal(requests, 0);
});

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

test("an unchanged failed deployment cannot retire a healthy predecessor", async () => {
  await assert.rejects(
    submitJob(job, {
      signal: signal(),
      get: async () => [
        { ID: "failed-canary", CreateIndex: 2, Status: "failed" },
      ],
      post: async () => ({ Diff: { Type: "None" }, JobModifyIndex: 10 }),
    }),
    /unchanged deployment failed-canary is failed/,
  );
});

test("an unchanged successful deployment is verified before retirement", async () => {
  const result = await submitJob(job, {
    signal: signal(),
    get: async () => [
      { ID: "qualified", CreateIndex: 2, Status: "successful" },
    ],
    post: async () => ({ Diff: { Type: "None" }, JobModifyIndex: 10 }),
  });
  assert.deepEqual(result, { deployment: "qualified" });
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

test("a newer Git release supersedes an entirely unplaced deployment", async () => {
  const result = await submitJob(job, {
    signal: signal(),
    get: async (path) =>
      path.endsWith("deployments")
        ? [
            {
              ID: "unplaced",
              Status: "running",
              TaskGroups: { replicas: { PlacedAllocs: 0 } },
            },
          ]
        : [],
    post: async (path) =>
      path.endsWith("plan")
        ? { Diff: { Type: "Edited" }, JobModifyIndex: 42 }
        : { EvalID: "replacement" },
    pause: async () => {
      throw new Error(
        "Must not wait for unavailable capacity before updating queued desired state",
      );
    },
  });
  assert.deepEqual(result, { evaluation: "replacement", previous: "unplaced" });
});

for (const prior of [
  { Status: "paused", TaskGroups: { replicas: { PlacedAllocs: 0 } } },
  { Status: "running", TaskGroups: { replicas: { PlacedAllocs: 1 } } },
  { Status: "running", TaskGroups: {} },
]) {
  test(`preserves paused, placed or unknown deployments: ${JSON.stringify(prior)}`, async () => {
    const controller = new AbortController();
    await assert.rejects(
      submitJob(job, {
        signal: controller.signal,
        get: async () => [{ ID: "existing", ...prior }],
        post: async (path) => {
          assert.ok(path.endsWith("plan"));
          return { Diff: { Type: "Edited" }, JobModifyIndex: 42 };
        },
        pause: async () => controller.abort(),
      }),
      /deadline/,
    );
  });
}

test("placement constraints are refreshed after a prior allocation drains", async () => {
  let draining = true;
  const result = await submitJob(job, {
    signal: signal(),
    prepare: async (source) => ({
      ...source,
      Constraints: [{ RTarget: draining ? "old" : "current" }],
    }),
    get: async (path) =>
      path.endsWith("deployments")
        ? []
        : draining
          ? [{ DesiredStatus: "stop", ClientStatus: "running" }]
          : [],
    pause: async () => {
      draining = false;
    },
    post: async (path, body) => {
      if (path.endsWith("plan"))
        return { Diff: { Type: "Added" }, JobModifyIndex: 0 };
      assert.equal(body.Job.Constraints[0].RTarget, "current");
      return { EvalID: "placed" };
    },
  });
  assert.equal(result.evaluation, "placed");
});
