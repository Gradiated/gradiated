import { waitForEvaluation } from "./wait-deployments.mjs";

export const replicaJobs = (jobs) =>
  jobs.flatMap((job) => {
    if (!job.Meta?.gradiated_model_id) return [job];
    if (job.TaskGroups.length !== 1)
      throw new Error(`${job.ID}: model jobs must have one replica group`);
    const count = job.TaskGroups[0].Count;
    if (count === 0) return [job];

    return Array.from({ length: count }, (_, index) => {
      const slot = count - index - 1;
      const replica = structuredClone(job);
      replica.ID = replica.Name = `${job.ID}-replica-${slot}`;
      replica.Meta.gradiated_replica_parent = job.ID;
      replica.Meta.gradiated_replica_slot = String(slot);
      replica.TaskGroups[0].Count = 1;
      replica.TaskGroups[0].Update.Canary = 1;
      replica.TaskGroups[0].Update.AutoPromote = false;
      return replica;
    });
  });

export const withPeerHostConstraints = async (job, { get }) => {
  const parent = job.Meta?.gradiated_replica_parent;
  if (
    !parent ||
    !job.TaskGroups.some(
      (group) =>
        group.Count > 0 &&
        group.Constraints?.some(
          (constraint) => constraint.Operand === "distinct_hosts",
        ),
    )
  )
    return job;

  const slot = job.Meta.gradiated_replica_slot;
  const siblings = (await get("/v1/jobs?meta=true")).filter(
    (sibling) =>
      !sibling.Stop &&
      sibling.ID !== job.ID &&
      (sibling.ID === parent ||
        sibling.Meta?.gradiated_replica_parent === parent),
  );
  const excluded = new Set();
  const qualified = new Map();
  for (const sibling of siblings) {
    const allocations = await get(
      `/v1/job/${encodeURIComponent(sibling.ID)}/allocations`,
    );
    for (const allocation of allocations) {
      const peerSlot =
        sibling.ID === parent
          ? allocation.Name?.match(/\[(\d+)\]$/)?.[1]
          : sibling.Meta?.gradiated_replica_slot;
      if (peerSlot === undefined)
        throw new Error(`${sibling.ID}: replica slot is missing`);
      if (
        peerSlot !== slot &&
        allocation.DesiredStatus === "run" &&
        !["complete", "failed", "lost"].includes(allocation.ClientStatus) &&
        allocation.NodeID
      ) {
        const child = sibling.ID !== parent;
        if (child && allocation.DeploymentStatus?.Healthy !== true) {
          excluded.add(allocation.NodeID);
          continue;
        }
        const previous = qualified.get(peerSlot);
        if (
          !previous ||
          Number(child) > Number(previous.child) ||
          (child === previous.child &&
            (allocation.CreateIndex ?? allocation.JobVersion ?? 0) >
              (previous.allocation.CreateIndex ??
                previous.allocation.JobVersion ??
                0))
        )
          qualified.set(peerSlot, { child, allocation });
      }
    }
  }
  for (const { allocation } of qualified.values())
    excluded.add(allocation.NodeID);
  const planned = structuredClone(job);
  planned.Constraints = [
    ...(planned.Constraints ?? []),
    ...[...excluded].sort().map((node) => ({
      LTarget: "${node.unique.id}",
      Operand: "!=",
      RTarget: node,
    })),
  ];
  return planned;
};

export const validateReplicaRetirement = async (jobs, { get }) => {
  const models = jobs.filter((job) => job.Meta?.gradiated_model_id);
  if (!models.length) return;
  const existing = await get("/v1/jobs?meta=true");
  for (const job of models) {
    const count = job.TaskGroups.reduce((sum, group) => sum + group.Count, 0);
    const candidates = existing.filter(
      (current) =>
        !current.Stop &&
        (current.ID === job.ID ||
          (current.Meta?.gradiated_replica_parent === job.ID &&
            Number(current.Meta.gradiated_replica_slot) >= count)),
    );
    for (const candidate of candidates) {
      const current = await get(`/v1/job/${encodeURIComponent(candidate.ID)}`);
      const active = current.TaskGroups.reduce(
        (sum, group) => sum + group.Count,
        0,
      );
      if (active > (candidate.ID === job.ID ? count : 0))
        throw new Error(
          `${job.ID}: reducing serving replicas requires a separate explicit retirement operation`,
        );
    }
  }
};

export const retireLegacyReplica = async (job, options) => {
  const { get, post } = options;
  const parent = job.Meta?.gradiated_replica_parent;
  if (!parent) return;
  const jobs = await get("/v1/jobs?meta=true");
  if (!jobs.some((item) => item.ID === parent && !item.Stop)) return;
  let legacy = await get(`/v1/job/${encodeURIComponent(parent)}`);
  const count = Number(job.Meta.gradiated_replica_slot);
  if (legacy.TaskGroups.length !== 1)
    throw new Error(`${parent}: legacy model must have one replica group`);
  if (legacy.TaskGroups[0].Count <= count) return;
  if (legacy.TaskGroups[0].Count !== count + 1)
    throw new Error(
      `${parent}: replicas must be migrated from highest index first`,
    );
  if (count > 0) {
    const allocations = await get(
      `/v1/job/${encodeURIComponent(parent)}/allocations`,
    );
    const retained = allocations.find(
      (allocation) =>
        allocation.DesiredStatus === "run" &&
        allocation.ClientStatus === "running" &&
        allocation.Name?.endsWith("[0]"),
    );
    if (!retained) throw new Error(`${parent}: retained replica is missing`);
    const { Versions } = await get(
      `/v1/job/${encodeURIComponent(parent)}/versions`,
    );
    const original = Versions.find(
      (version) => version.Version === retained.JobVersion,
    );
    if (!original)
      throw new Error(`${parent}: retained job version is missing`);
    legacy = { ...original, JobModifyIndex: legacy.JobModifyIndex };
  }
  legacy.TaskGroups[0].Count = count;
  legacy.TaskGroups[0].Update.Canary = count;
  legacy.TaskGroups[0].Update.AutoPromote = count > 0;
  legacy.TaskGroups[0].Update.AutoRevert = true;
  const result = await post("/v1/jobs", {
    Job: legacy,
    EnforceIndex: true,
    JobModifyIndex: legacy.JobModifyIndex,
  });
  await waitForEvaluation(result.EvalID, "", options);
};

export const releaseFailedMigration = async (job, { get, post }) => {
  const parent = job.Meta?.gradiated_replica_parent;
  if (!parent) return;
  const jobs = await get("/v1/jobs?meta=true");
  if (
    !jobs.some((current) => current.ID === parent && !current.Stop) ||
    !jobs.some((current) => current.ID === job.ID && !current.Stop)
  )
    return;
  const legacy = await get(`/v1/job/${encodeURIComponent(parent)}/allocations`);
  const slot = job.Meta.gradiated_replica_slot;
  if (
    !legacy.some(
      (allocation) =>
        allocation.Name?.endsWith(`[${slot}]`) &&
        allocation.DesiredStatus === "run" &&
        allocation.ClientStatus === "running" &&
        allocation.DeploymentStatus?.Healthy === true,
    )
  )
    return;
  const current = await get(`/v1/job/${encodeURIComponent(job.ID)}`);
  const stopped = structuredClone(current);
  for (const group of stopped.TaskGroups) {
    group.Count = 0;
    group.Update.Canary = 0;
  }
  await post("/v1/jobs", {
    Job: stopped,
    EnforceIndex: true,
    JobModifyIndex: current.JobModifyIndex,
  });
};
