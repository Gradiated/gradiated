import { spawn } from "node:child_process";
import { setTimeout as delay } from "node:timers/promises";

const verifyOnce = (input, signal, spawnProcess) =>
  new Promise((resolve, reject) => {
    const child = spawnProcess(
      "kubectl",
      [
        "-n",
        "gradiated",
        "exec",
        "-i",
        "-c",
        "worker",
        "deployment/worker",
        "--",
        "node",
        "services/worker/dist/verify-model.js",
      ],
      { signal, timeout: 8 * 60_000, stdio: ["pipe", "inherit", "inherit"] },
    );
    child.on("error", reject);
    child.stdin.on("error", reject);
    child.on("close", (code) => {
      if (code === 0) resolve();
      else
        reject(
          Object.assign(
            new Error(`Production SDK verification exited with ${code}`),
            { exitCode: code },
          ),
        );
    });
    child.stdin.end(JSON.stringify(input));
  });

export const verifyInProduction = async (
  input,
  signal,
  { spawnProcess = spawn, pause = delay } = {},
) => {
  for (let attempt = 1; ; attempt++) {
    signal?.throwIfAborted();
    try {
      await verifyOnce(input, signal, spawnProcess);
      return;
    } catch (error) {
      // A rolling worker deployment can terminate kubectl exec. Re-run the
      // complete SDK check on a current worker; never retry assertion failures.
      if (
        signal?.aborted ||
        attempt >= 3 ||
        ![137, 143].includes(error.exitCode)
      )
        throw error;
      await pause(5000, undefined, { signal });
    }
  }
};

export const validateModelRollout = (job) => {
  if (job.Meta?.gradiated_sdk_verification !== "true") return;

  const groups = job.TaskGroups.filter((group) => group.Count > 0);
  if (
    groups.some(
      (group) =>
        group.Update?.HealthCheck !== "manual" ||
        group.Update.Canary !== group.Count ||
        (job.Meta.gradiated_replica_parent
          ? group.Update.AutoPromote !== false
          : group.Update.AutoPromote !== true) ||
        group.Update.AutoRevert !== true,
    )
  )
    throw new Error(
      "SDK verification requires manual health, full-count canaries and automatic revert to preserve serving capacity; singleton replicas use manual promotion",
    );
};

export const createVerificationGate = async (
  deployment,
  { get, post, verify, signal, now = Date.now },
) => {
  const { Versions } = await get(
    `/v1/job/${encodeURIComponent(deployment.JobID)}/versions`,
    signal,
  );
  const job = Versions.find(
    (version) => version.Version === deployment.JobVersion,
  );
  if (!job) throw new Error("Deployment job version is missing");
  if (job.Meta?.gradiated_sdk_verification !== "true") return undefined;

  const release = JSON.parse(job.Meta.gradiated_release);
  const groups = job.TaskGroups.filter((group) => group.Count > 0);
  const input = {
    modelId: job.Meta.gradiated_model_id,
    runtimeRevision: release.runtime_revision,
    ...(job.Meta.gradiated_replica_parent ||
    (groups.length === 1 && groups[0].Count === 1)
      ? { replicaRollout: true }
      : {}),
    ...(release.protocol ? { protocol: release.protocol } : {}),
  };
  if (!groups.length) return undefined;
  validateModelRollout(job);

  const allocations = async () =>
    (
      (await get(
        `/v1/deployment/allocations/${encodeURIComponent(deployment.ID)}`,
        signal,
      )) ?? []
    ).filter(
      (allocation) =>
        allocation.JobVersion === deployment.JobVersion &&
        allocation.DesiredStatus === "run" &&
        allocation.ClientStatus === "running",
    );
  const complete = (items) =>
    groups.every(
      (group) =>
        items.filter((allocation) => allocation.TaskGroup === group.Name)
          .length === group.Count,
    );

  const stableSince = new Map();
  const checksHealthy = async (allocation) => {
    const checks = Object.values(
      (await get(`/v1/allocation/${allocation.ID}/checks`, signal)) ?? {},
    );
    const healthy =
      checks.length > 0 &&
      checks.every(
        (check) =>
          check.Status === "success" &&
          Number.isFinite(check.Timestamp) &&
          check.Timestamp <= now() / 1000 + 5 &&
          now() / 1000 - check.Timestamp <= 60,
      );
    if (!healthy) stableSince.delete(allocation.ID);
    return healthy;
  };

  const promote = async () => {
    if (groups.every((group) => group.Update.AutoPromote)) return;
    const state = await get(`/v1/deployment/${deployment.ID}`, signal);
    if (
      !Object.values(state.TaskGroups ?? {}).some(
        (group) => group.DesiredCanaries > 0 && !group.Promoted,
      )
    )
      return;
    const ready = await allocations();
    if (
      !complete(ready) ||
      ready.some((allocation) => allocation.DeploymentStatus?.Healthy !== true)
    )
      return;
    try {
      await verify(
        {
          ...input,
          stage: "serving",
          deploymentIds: ready.map((allocation) => allocation.ID),
        },
        signal,
      );
    } catch (error) {
      if (!signal.aborted)
        await post(`/v1/deployment/fail/${deployment.ID}`, {
          DeploymentID: deployment.ID,
        });
      throw error;
    }
    for (const allocation of ready)
      if (!(await checksHealthy(allocation))) return;
    await post(`/v1/deployment/promote/${deployment.ID}`, {
      DeploymentID: deployment.ID,
      All: true,
    });
  };

  return {
    qualify: async () => {
      const candidates = await allocations();
      if (!complete(candidates)) return;

      const pending = candidates.filter(
        (allocation) => allocation.DeploymentStatus?.Healthy !== true,
      );
      if (!pending.length) return promote();
      let stable = true;
      for (const allocation of pending) {
        if (!(await checksHealthy(allocation))) {
          stable = false;
          continue;
        }
        if (!stableSince.has(allocation.ID))
          stableSince.set(allocation.ID, now());
        const minimum =
          groups.find((group) => group.Name === allocation.TaskGroup).Update
            .MinHealthyTime ?? 0;
        if (now() - stableSince.get(allocation.ID) < minimum / 1_000_000)
          stable = false;
      }
      if (!stable) return;

      try {
        await verify(
          {
            ...input,
            stage: "canary",
            deploymentIds: pending.map((allocation) => allocation.ID),
          },
          signal,
        );
      } catch (error) {
        if (!signal.aborted)
          await post(`/v1/deployment/fail/${deployment.ID}`, {
            DeploymentID: deployment.ID,
          });
        throw error;
      }

      const current = await allocations();
      const verified = pending.filter((allocation) =>
        current.some((item) => item.ID === allocation.ID),
      );
      for (const allocation of verified)
        if (!(await checksHealthy(allocation))) return;
      if (verified.length)
        await post(`/v1/deployment/allocation-health/${deployment.ID}`, {
          DeploymentID: deployment.ID,
          HealthyAllocationIDs: verified.map((allocation) => allocation.ID),
        });
      await promote();
    },
    finish: async () => {
      const promoted = await allocations();
      if (!complete(promoted))
        throw new Error("Promoted deployment is missing running allocations");
      await verify(
        {
          ...input,
          stage: "serving",
          deploymentIds: promoted.map((allocation) => allocation.ID),
        },
        signal,
      );
    },
  };
};
