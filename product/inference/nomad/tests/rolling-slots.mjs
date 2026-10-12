import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { setTimeout as delay } from "node:timers/promises";
import {
  readModelAllocations,
  allocationIsGone,
} from "../../../services/worker/src/nomad-allocations.ts";
import {
  createControlDatabase,
  createCatalogService,
  createInstanceService,
  createNomadDeploymentStore,
  catalogModels,
} from "../../../packages/control/dist/index.js";
import {
  replicaJobs,
  retireLegacyReplica,
  releaseFailedMigration,
} from "../../../../tools/nomad/replica-jobs.mjs";
import { submitJob, deployJobs } from "../../../../tools/nomad/submit-jobs.mjs";
import {
  waitForEvaluation,
  waitForDeployment,
} from "../../../../tools/nomad/wait-deployments.mjs";
const execute = promisify(execFile);
const controller = new AbortController();
const signal = AbortSignal.any([
  controller.signal,
  AbortSignal.timeout(360_000),
]);
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

const { database, pool } = createControlDatabase(process.env.DATABASE_URL, 2);
const store = createNomadDeploymentStore(database);
const catalog = createCatalogService(database);
const instances = createInstanceService(database);
const template = await call("/v1/job/fake-runtime");
const original = (await call("/v1/job/fake-runtime/allocations")).filter(
  (a) => a.DesiredStatus === "run",
);
await catalog.upsertModel({
  ...catalogModels[0],
  id: "synthetic/model",
  name: "Synthetic",
});
const host = await instances.register({
  provider: "runpod",
  providerAccountId: "test",
  providerInstanceId: "podsynthetic",
  region: "test",
  faultDomain: "test",
  sku: "synthetic",
});
const nodeId = "00000000-0000-4000-8000-000000000001";
await instances.bindNomadNode(host.id, nodeId);
await instances.setServingUrl(host.id, `http://gpu-${host.id}.tailscale-inference.svc.cluster.local:8888`);
const get = async (path) => {
  const response = await call(path);
  if (path.endsWith("/versions")) {
    for (const job of response.Versions) {
      job.Meta.gradiated_release = JSON.stringify({
        schema_version: 1,
        runtime_revision: job.Meta.gradiated_release
          ? JSON.parse(job.Meta.gradiated_release).runtime_revision
          : "v1",
        model_path: "synthetic/model",
        model_revision: "revision",
        tokenizer_path: "synthetic/tokenizer",
        tokenizer_revision: "revision",
      });
    }
  }
  return response;
};
const snapshots = [];
let observing = true;
let lastRead;
const observe = async () => {
  await store.reconcile({
    running: async () =>
      (lastRead = await readModelAllocations(get, () => {
        throw new Error("Invalid allocation");
      })).map((allocation) => ({ ...allocation, nodeId })),
    isGone: (id) => allocationIsGone(get, id),
  });
  const serving = await store.replicas();
  const allocations = (await call("/v1/allocations")).filter(
    (a) => a.JobID !== "host-proxy-loopback" && a.ClientStatus === "running",
  );
  snapshots.push({ available: serving.length, running: allocations.length });
  if (serving.length !== 2) {
    for (const replica of serving) {
      const raw = await call(`/v1/allocation/${replica.id}`);
      console.log(
        JSON.stringify({
          event: "unexpected_serving_allocation",
          ID: raw.ID,
          Name: raw.Name,
          ClientStatus: raw.ClientStatus,
          DesiredStatus: raw.DesiredStatus,
          JobVersion: raw.JobVersion,
          DeploymentStatus: raw.DeploymentStatus,
        }),
      );
    }
  }
  assert.equal(
    serving.length,
    2,
    `Serving capacity changed: ${JSON.stringify({ serving, lastRead, allocations: allocations.map((a) => ({ ID: a.ID, Name: a.Name, JobID: a.JobID, JobVersion: a.JobVersion, DesiredStatus: a.DesiredStatus, DeploymentStatus: a.DeploymentStatus })) })}`,
  );
  assert.ok(allocations.length >= 2, "Lost a running serving replica");
  assert.ok(allocations.length <= 3, "Used more than one staging slot");
  for (const replica of serving) {
    const checks = Object.values(
      (await call(`/v1/allocation/${replica.id}/checks`)) ?? {},
    );
    if (!checks.length) {
      const current = await call(`/v1/allocation/${replica.id}`);
      assert.notEqual(
        current.DesiredStatus,
        "run",
        "Serving replica has no checks",
      );
      continue;
    }
    assert.ok(
      checks.length && checks.every((c) => c.Status === "success"),
      "Serving replica lost health",
    );
  }
};
const verify = async (input) => {
  if (input.stage === "serving")
    await wait(async () => {
      const rows = await store.verificationReplicas(
        "synthetic/model",
        input.deploymentIds,
      );
      return input.deploymentIds.every((id) =>
        rows.some((row) => row.id === id && row.status === "available"),
      );
    });
  for (const id of input.deploymentIds) await verifyRoute(id);
};
const options = {
  get: (path) => call(path),
  post: call,
  signal,
  pause: () => delay(500, undefined, { signal }),
  verify,
};
const rollout = async (jobs, override = {}) =>
  deployJobs(jobs, async (job) => {
    const opts = { ...options, ...override };
    try {
      const registered = await submitJob(job, opts);
      if (registered.deployment)
        await waitForDeployment(registered.deployment, opts);
      if (registered.evaluation)
        await waitForEvaluation(
          registered.evaluation,
          registered.previous,
          opts,
        );
      await retireLegacyReplica(job, opts);
    } catch (error) {
      await releaseFailedMigration(job, opts);
      throw error;
    }
  });
const jobs = replicaJobs([
  {
    ...template,
    Meta: {
      ...template.Meta,
      gradiated_sdk_verification: "true",
      gradiated_release: '{"runtime_revision":"v2"}',
    },
  },
]);
for (const job of jobs) {
  Object.assign(job.TaskGroups[0].Update, {
    HealthCheck: "manual",
    HealthyDeadline: 30_000_000_000,
    ProgressDeadline: 40_000_000_000,
  });
  job.TaskGroups[0].Tasks[0].Env = { RELEASE: "v2" };
}
await observe();
const watching = (async () => {
  while (observing) {
    await observe();
    await delay(100, undefined, { signal });
  }
})();
void watching.catch((error) => controller.abort(error));
try {
  await assert.rejects(
    rollout(jobs, {
      verify: async () => {
        throw new Error("Initial staging SDK rejection");
      },
    }),
    /Initial staging SDK rejection/,
  );
  assert.equal((await call(`/v1/job/${jobs[0].ID}`)).TaskGroups[0].Count, 0);
  console.log(
    "Failed initial staging was released while both legacy replicas kept serving",
  );
  await rollout(jobs);
  assert.equal((await call("/v1/job/fake-runtime")).TaskGroups[0].Count, 0);
  console.log(
    "Migrated two replicas into singleton jobs using one staging slot without changing serving capacity",
  );
  for (const job of jobs) {
    job.Meta.gradiated_release = '{"runtime_revision":"v3"}';
    job.TaskGroups[0].Tasks[0].Env = { RELEASE: "v3" };
  }
  await rollout(jobs);
  console.log(
    "Rolled both replicas successfully using the same single staging slot",
  );
  for (const failedStage of ["canary", "serving"]) {
    const failing = structuredClone(jobs);
    for (const job of failing)
      job.TaskGroups[0].Tasks[0].Env = {
        RELEASE: `sdk-failure-${failedStage}`,
      };
    let attempts = 0;
    await assert.rejects(
      rollout(failing, {
        verify: async (input) => {
          if (input.stage !== failedStage) return verify(input);
          attempts++;
          if (failedStage === "serving") await verify(input);
          throw new Error("Synthetic SDK rejection");
        },
      }),
      /Synthetic SDK rejection/,
    );
    assert.equal(attempts, 1);
    const rollback = (await call(`/v1/job/${jobs[0].ID}/deployments`)).sort(
      (a, b) => b.CreateIndex - a.CreateIndex,
    )[0];
    await waitForDeployment(rollback.ID, options);
    console.log(
      `${failedStage} SDK rejection failed the rollout, retained both serving replicas and skipped the next replica`,
    );
  }
  const unhealthy = structuredClone(jobs[1]);
  unhealthy.TaskGroups[0].Tasks[0].Config = { command: "/bin/false", args: [] };
  unhealthy.TaskGroups[0].Update.HealthyDeadline = 10_000_000_000;
  unhealthy.TaskGroups[0].Update.ProgressDeadline = 15_000_000_000;
  await assert.rejects(rollout([unhealthy]), /is failed/);
  console.log(
    "Health rejection failed the rollout while both replicas kept serving",
  );
} finally {
  observing = false;
  await watching;
  await observe();
  await pool.end();
}
console.log(
  JSON.stringify({
    event: "rolling_slot_capacity",
    samples: snapshots.length,
    serving: [...new Set(snapshots.map((s) => s.available))],
    maximumRunning: Math.max(...snapshots.map((s) => s.running)),
  }),
);
