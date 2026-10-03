import assert from "node:assert/strict";
import { test } from "node:test";
import {
  replicaJobs,
  releaseFailedMigration,
  retireLegacyReplica,
  withPeerHostConstraints,
  validateReplicaRetirement,
} from "./replica-jobs.mjs";

const model = (count) => ({
  ID: "kev",
  Name: "kev",
  Meta: { gradiated_model_id: "model" },
  TaskGroups: [{ Count: count, Update: { Canary: count, AutoPromote: true } }],
});

test("replicated models become singleton jobs in safe migration order", () => {
  const source = model(2);
  const jobs = replicaJobs([source]);
  assert.deepEqual(
    jobs.map((job) => job.ID),
    ["kev-replica-1", "kev-replica-0"],
  );
  assert.ok(
    jobs.every(
      (job) =>
        job.TaskGroups[0].Count === 1 && job.TaskGroups[0].Update.Canary === 1,
    ),
  );
  assert.deepEqual(
    jobs.map((job) => job.Meta.gradiated_replica_slot),
    ["1", "0"],
  );
  assert.equal(source.TaskGroups[0].Count, 2);
  assert.equal(replicaJobs([model(1)])[0].ID, "kev-replica-0");
  assert.deepEqual(replicaJobs([model(0)]), [model(0)]);
});

test("legacy scale-down preserves other replicas and uses the observed modify index", async () => {
  const legacy = { ...model(2), JobModifyIndex: 42 };
  const posts = [];
  await retireLegacyReplica(replicaJobs([legacy])[0], {
    signal: new AbortController().signal,
    get: async (path) => {
      if (path === "/v1/jobs?meta=true") return [{ ID: "kev", Stop: false }];
      if (path === "/v1/job/kev") return legacy;
      if (path === "/v1/job/kev/allocations")
        return [
          {
            Name: "kev.replicas[0]",
            DesiredStatus: "run",
            ClientStatus: "running",
            JobVersion: 1,
          },
        ];
      if (path === "/v1/job/kev/versions")
        return { Versions: [{ ...legacy, Version: 1 }] };
      if (path === "/v1/evaluation/scale") return { Status: "complete" };
      throw new Error(path);
    },
    post: async (path, body) => {
      posts.push({ path, body });
      return { EvalID: "scale" };
    },
  });
  assert.equal(posts[0].body.Job.TaskGroups[0].Count, 1);
  assert.equal(posts[0].body.JobModifyIndex, 42);
  assert.equal(posts[0].body.EnforceIndex, true);
});

test("migration refuses to retire multiple old replicas at once", async () => {
  const legacy = model(2);
  await assert.rejects(
    retireLegacyReplica(replicaJobs([legacy])[1], {
      get: async (path) =>
        path.endsWith("meta=true") ? [{ ID: "kev" }] : legacy,
      post: async () => {
        throw new Error("must not register");
      },
    }),
    /highest index first/,
  );
});

test("singleton host constraints exclude both legacy and migrated peer slots", async () => {
  const source = model(2);
  source.TaskGroups[0].Constraints = [{ Operand: "distinct_hosts" }];
  const job = replicaJobs([source])[0];
  const planned = await withPeerHostConstraints(job, {
    get: async (path) => {
      if (path === "/v1/jobs?meta=true")
        return [
          { ID: "kev" },
          {
            ID: "kev-replica-0",
            Meta: {
              gradiated_replica_parent: "kev",
              gradiated_replica_slot: "0",
            },
          },
        ];
      if (path === "/v1/job/kev/allocations")
        return [
          {
            Name: "kev.replicas[0]",
            NodeID: "legacy-peer",
            DesiredStatus: "run",
            ClientStatus: "running",
          },
          {
            Name: "kev.replicas[1]",
            NodeID: "own-old",
            DesiredStatus: "run",
            ClientStatus: "running",
          },
          {
            Name: "kev.replicas[0]",
            NodeID: "retired-peer",
            DesiredStatus: "stop",
            ClientStatus: "running",
          },
        ];
      if (path === "/v1/job/kev-replica-0/allocations")
        return [
          {
            NodeID: "migrated-peer",
            DesiredStatus: "run",
            ClientStatus: "running",
          },
        ];
      throw new Error(path);
    },
  });
  assert.deepEqual(
    planned.Constraints.map((constraint) => constraint.RTarget),
    ["legacy-peer", "migrated-peer"],
  );
  assert.equal(job.Constraints, undefined);
});

test("models without host anti-affinity need no sibling exclusions", async () => {
  const job = replicaJobs([model(1)])[0];
  assert.equal(
    await withPeerHostConstraints(job, {
      get: async () => {
        throw new Error("unexpected read");
      },
    }),
    job,
  );
});

test("disabling a migrated model requires explicit retirement before submission", async () => {
  await assert.rejects(
    validateReplicaRetirement([model(0)], {
      get: async (path) =>
        path === "/v1/jobs?meta=true"
          ? [
              {
                ID: "kev-replica-0",
                Meta: {
                  gradiated_replica_parent: "kev",
                  gradiated_replica_slot: "0",
                },
              },
            ]
          : model(1),
    }),
    /separate explicit retirement/,
  );
});

test("reducing an existing legacy model requires explicit retirement", async () => {
  await assert.rejects(
    validateReplicaRetirement([model(1)], {
      get: async (path) =>
        path === "/v1/jobs?meta=true" ? [{ ID: "kev" }] : model(2),
    }),
    /separate explicit retirement/,
  );
});

test("an already retired model can remain disabled", async () => {
  await validateReplicaRetirement([model(0)], {
    get: async (path) =>
      path === "/v1/jobs?meta=true" ? [{ ID: "kev" }] : model(0),
  });
});

test("peer placement releases superseded nodes after a qualified cutover", async () => {
  const source = model(2);
  source.TaskGroups[0].Constraints = [{ Operand: "distinct_hosts" }];
  const job = replicaJobs([source])[0];
  const planned = await withPeerHostConstraints(job, {
    get: async (path) =>
      path === "/v1/jobs?meta=true"
        ? [
            { ID: "kev" },
            {
              ID: "kev-replica-0",
              Meta: {
                gradiated_replica_parent: "kev",
                gradiated_replica_slot: "0",
              },
            },
          ]
        : path === "/v1/job/kev/allocations"
          ? [
              {
                Name: "kev.replicas[0]",
                NodeID: "legacy",
                DesiredStatus: "run",
                ClientStatus: "running",
              },
            ]
          : [
              {
                NodeID: "old",
                JobVersion: 0,
                DesiredStatus: "run",
                ClientStatus: "running",
                DeploymentStatus: { Healthy: true },
              },
              {
                NodeID: "replacement",
                JobVersion: 1,
                DesiredStatus: "run",
                ClientStatus: "running",
                DeploymentStatus: { Healthy: true },
              },
            ],
  });
  assert.deepEqual(
    planned.Constraints.map((constraint) => constraint.RTarget),
    ["replacement"],
  );
});

test("failed initial migration releases staging only while the healthy legacy slot remains", async () => {
  for (const retained of [true, false]) {
    const job = replicaJobs([model(2)])[0];
    const writes = [];
    await releaseFailedMigration(job, {
      get: async (path) =>
        path === "/v1/jobs?meta=true"
          ? [{ ID: "kev" }, { ID: job.ID }]
          : path.endsWith("allocations")
            ? [
                {
                  Name: "kev.replicas[1]",
                  DesiredStatus: retained ? "run" : "stop",
                  ClientStatus: "running",
                  DeploymentStatus: { Healthy: true },
                },
              ]
            : { ...job, JobModifyIndex: 123 },
      post: async (path, body) => writes.push(body),
    });
    assert.equal(writes.length, retained ? 1 : 0);
    if (retained) {
      assert.equal(writes[0].Job.TaskGroups[0].Count, 0);
      assert.equal(writes[0].Job.TaskGroups[0].Update.Canary, 0);
      assert.equal(writes[0].EnforceIndex, true);
      assert.equal(writes[0].JobModifyIndex, 123);
    }
  }
});

test("legacy retirement does not replay serving verification for its previous replica count", async () => {
  for (const count of [1, 2]) {
    const original = {
      ...model(count),
      Version: 1,
      JobModifyIndex: 42,
      Meta: {
        gradiated_model_id: "model",
        gradiated_sdk_verification: "true",
        gradiated_release: JSON.stringify({ runtime_revision: "legacy" }),
      },
    };
    Object.assign(original.TaskGroups[0], { Name: "replicas" });
    Object.assign(original.TaskGroups[0].Update, {
      HealthCheck: "manual",
      AutoRevert: true,
    });
    const legacy = structuredClone(original);
    const retained = {
      ID: "retained",
      Name: "kev.replicas[0]",
      TaskGroup: "replicas",
      DesiredStatus: "run",
      ClientStatus: "running",
      JobVersion: 1,
    };
    let checks = 0;
    await retireLegacyReplica(replicaJobs([legacy])[0], {
      signal: new AbortController().signal,
      verify: async () => {
        checks++;
      },
      get: async (path) => {
        if (path === "/v1/jobs?meta=true") return [{ ID: "kev", Stop: false }];
        if (path === "/v1/job/kev") return legacy;
        if (path === "/v1/job/kev/allocations") return [retained];
        if (path === "/v1/job/kev/versions")
          return { Versions: [structuredClone(original)] };
        if (path === "/v1/evaluation/scale")
          return { Status: "complete", DeploymentID: "previous" };
        if (path === "/v1/deployment/previous")
          return {
            ID: "previous",
            JobID: "kev",
            JobVersion: 1,
            Status: "successful",
          };
        if (path === "/v1/deployment/allocations/previous")
          return count === 2 ? [retained] : [];
        throw new Error(path);
      },
      post: async () => ({ EvalID: "scale" }),
    });
    assert.equal(checks, 0);
  }
});
