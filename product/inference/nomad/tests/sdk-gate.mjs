import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { setTimeout as delay } from "node:timers/promises";
import { submitJob } from "../../../../tools/nomad/submit-jobs.mjs";
import { waitForDeployment } from "../../../../tools/nomad/wait-deployments.mjs";

const execute = promisify(execFile);
const signal = AbortSignal.timeout(180_000);
const call = async (path, body) => {
  const { stdout } = await execute(
    "docker",
    [
      "exec",
      process.env.TEST_CONTAINER,
      "curl",
      "-fsS",
      "--max-time",
      "5",
      "-H",
      `x-nomad-token: ${process.env.TEST_NOMAD_TOKEN}`,
      ...(body
        ? ["-H", "content-type: application/json", "-d", JSON.stringify(body)]
        : []),
      `http://127.0.0.1:4646${path}`,
    ],
    { signal },
  );
  return JSON.parse(stdout);
};
const wait = async (predicate) => {
  while (!(await predicate())) await delay(500, undefined, { signal });
};
const verifyRoute = async (id) => {
  let consecutiveReady = 0;
  await wait(async () => {
    const { stdout } = await execute(
      "docker",
      [
        "exec",
        process.env.TEST_CONTAINER,
        "curl",
        "-sS",
        "--max-time",
        "3",
        "-w",
        " %{http_code}",
        "-H",
        "Authorization: Bearer synthetic_runtime_token_0000000000000000",
        `http://127.0.0.1:8888/alloc/${id}/ready`,
      ],
      { signal },
    );
    consecutiveReady =
      stdout.startsWith(id) && stdout.endsWith(" 200")
        ? consecutiveReady + 1
        : 0;
    return consecutiveReady >= 3;
  });
};
const allocations = () => call("/v1/job/fake-runtime/allocations");
const original = (await allocations())
  .filter((allocation) => allocation.ClientStatus === "running")
  .map((allocation) => allocation.ID);
const job = await call("/v1/job/fake-runtime");
job.Meta = {
  gradiated_model_id: "synthetic/model",
  gradiated_sdk_verification: "true",
  gradiated_release: '{"runtime_revision":"v2"}',
};
Object.assign(job.TaskGroups[0].Update, {
  HealthCheck: "manual",
  Canary: 2,
  HealthyDeadline: 120_000_000_000,
  ProgressDeadline: 150_000_000_000,
});
job.TaskGroups[0].Tasks[0].Env = { RELEASE: "v2" };
const submitted = await call("/v1/jobs", { Job: job });
let deployment;
await wait(async () => {
  deployment = (await call(`/v1/evaluation/${submitted.EvalID}`)).DeploymentID;
  return deployment;
});
await wait(
  async () =>
    (await allocations()).filter(
      (allocation) =>
        allocation.JobVersion === job.Version + 1 &&
        allocation.ClientStatus === "running",
    ).length === 2,
);
await delay(3000, undefined, { signal });
assert.equal((await call(`/v1/deployment/${deployment}`)).Status, "running");
assert.ok(
  (await allocations())
    .filter((allocation) => original.includes(allocation.ID))
    .every((allocation) => allocation.DesiredStatus === "run"),
);
const verified = [];
await waitForDeployment(deployment, {
  get: (path) => call(path),
  post: call,
  signal,
  pause: () => delay(500, undefined, { signal }),
  verify: async (input) => {
    if (input.stage === "canary")
      for (const id of input.deploymentIds) {
        await verifyRoute(id);
        verified.push(id);
      }
  },
});
assert.equal(new Set(verified).size, 2);
assert.equal((await call(`/v1/deployment/${deployment}`)).Status, "successful");
console.log(
  "Manual-health rollout retained old replicas until both exact canaries passed verification",
);

await wait(async () =>
  (await allocations())
    .filter((allocation) => original.includes(allocation.ID))
    .every((allocation) => allocation.ClientStatus === "complete"),
);
const stopped = verified[0];
await call(`/v1/allocation/${stopped}/stop`, { Reschedule: true });
let replacement;
await wait(async () => {
  replacement = (await allocations()).find(
    (allocation) =>
      allocation.JobVersion === job.Version + 1 &&
      allocation.ID !== stopped &&
      !verified.includes(allocation.ID) &&
      allocation.ClientStatus === "running",
  );
  return replacement;
});
assert.equal((await call(`/v1/deployment/${deployment}`)).Status, "successful");
verified[0] = replacement.ID;
await verifyRoute(replacement.ID);
console.log(
  "A verified release rescheduled a stopped allocation without another CI promotion",
);

job.TaskGroups[0].Tasks[0].Env = { RELEASE: "v3" };
const failed = await call("/v1/jobs", { Job: job });
let failedDeployment;
await wait(async () => {
  failedDeployment = (await call(`/v1/evaluation/${failed.EvalID}`))
    .DeploymentID;
  return failedDeployment;
});
await assert.rejects(
  waitForDeployment(failedDeployment, {
    get: (path) => call(path),
    post: call,
    signal,
    pause: () => delay(500, undefined, { signal }),
    verify: async () => {
      throw new Error("Synthetic SDK rejection");
    },
  }),
  /Synthetic SDK rejection/,
);
assert.equal(
  (await call(`/v1/deployment/${failedDeployment}`)).Status,
  "failed",
);
const remaining = await allocations();
assert.ok(
  verified.every((id) =>
    remaining.some(
      (allocation) =>
        allocation.ID === id &&
        allocation.ClientStatus === "running" &&
        allocation.DesiredStatus === "run",
    ),
  ),
);
console.log(
  "A rejected replacement failed its deployment while the verified release kept serving",
);

const initialJob = {
  ...structuredClone(job),
  ID: "initial-runtime",
  Name: "initial-runtime",
};
initialJob.TaskGroups[0].Count = 1;
initialJob.TaskGroups[0].Update.Canary = 1;
const initial = await call("/v1/jobs", { Job: initialJob });
let initialDeployment;
await wait(async () => {
  initialDeployment = (await call(`/v1/evaluation/${initial.EvalID}`))
    .DeploymentID;
  return initialDeployment;
});
const initialVerified = new Set();
await waitForDeployment(initialDeployment, {
  get: (path) => call(path),
  post: call,
  signal,
  pause: () => delay(500, undefined, { signal }),
  verify: async (input) => {
    if (input.stage === "canary")
      for (const id of input.deploymentIds) {
        await verifyRoute(id);
        initialVerified.add(id);
      }
  },
});
assert.equal(initialVerified.size, 1);
console.log(
  "Initial deployment also required verification of its allocation identity",
);

const scaledJob = await call("/v1/job/initial-runtime");
scaledJob.TaskGroups[0].Count = 2;
scaledJob.TaskGroups[0].Update.Canary = 2;
const scaled = await call("/v1/jobs", { Job: scaledJob });
let scaledDeployment;
await wait(async () => {
  scaledDeployment = (await call(`/v1/evaluation/${scaled.EvalID}`))
    .DeploymentID;
  return scaledDeployment;
});
const scaledVerified = new Set();
await waitForDeployment(scaledDeployment, {
  get: (path) => call(path),
  post: call,
  signal,
  pause: () => delay(500, undefined, { signal }),
  verify: async (input) => {
    if (input.stage === "canary")
      for (const id of input.deploymentIds) {
        await verifyRoute(id);
        scaledVerified.add(id);
      }
  },
});
assert.equal(scaledVerified.size, 2);
assert.ok([...initialVerified].every((id) => scaledVerified.has(id)));
console.log(
  "Scaling one replica to two qualified the new and reused allocations",
);

const blockedJob = await call("/v1/job/initial-runtime");
blockedJob.Constraints = [
  {
    LTarget: "${node.class}",
    RTarget: "unavailable-test-capacity",
    Operand: "=",
  },
];
blockedJob.TaskGroups[0].Tasks[0].Env = { RELEASE: "blocked" };
const blocked = await call("/v1/jobs", { Job: blockedJob });
let blockedDeployment;
await wait(async () => {
  blockedDeployment = (await call(`/v1/evaluation/${blocked.EvalID}`))
    .DeploymentID;
  return blockedDeployment;
});
assert.equal(
  (await call(`/v1/deployment/${blockedDeployment}`)).TaskGroups.replicas
    .PlacedAllocs,
  0,
);
blockedJob.Constraints = [];
blockedJob.TaskGroups[0].Tasks[0].Env = { RELEASE: "current-git" };
const replacementEvaluation = await submitJob(blockedJob, {
  get: (path) => call(path),
  post: call,
  signal,
  pause: () => delay(500, undefined, { signal }),
});
assert.ok(replacementEvaluation.evaluation);
const serving = await call("/v1/job/initial-runtime/allocations");
assert.ok(
  [...scaledVerified].every((id) =>
    serving.some(
      (allocation) =>
        allocation.ID === id &&
        allocation.ClientStatus === "running" &&
        allocation.DesiredStatus === "run",
    ),
  ),
);
assert.equal(
  (await call(`/v1/deployment/${blockedDeployment}`)).Status,
  "cancelled",
);
console.log(
  "A newer Git release superseded an unplaced rollout without stopping the serving release",
);
