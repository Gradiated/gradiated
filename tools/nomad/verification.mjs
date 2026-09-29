import { execFile } from "node:child_process";

const execute = (args, input, signal) =>
  new Promise((resolve, reject) => {
    const child = execFile(
      "kubectl",
      args,
      { signal, timeout: 8 * 60_000, maxBuffer: 1024 * 1024 },
      (error, stdout, stderr) => {
        if (error) {
          const details = stderr.split("\n").flatMap((line) => {
            try {
              const record = JSON.parse(line);
              if (record.event !== "model_sdk_verification_failed") return [];
              const stage = [
                "reconciliation",
                "key_issue",
                "inference",
              ].includes(record.stage)
                ? record.stage
                : "unknown";
              return [
                `${stage}${Number.isInteger(record.status) ? ` HTTP ${record.status}` : ""}`,
              ];
            } catch {
              return [];
            }
          });
          reject(
            new Error(
              `Production SDK verification command failed${details.length ? `: ${details.join(", ")}` : ""}`,
            ),
          );
        } else resolve(stdout);
      },
    );
    child.stdin.end(input);
  });

export const verifyInProduction = async (input, signal) => {
  const pods = JSON.parse(
    await execute(
      [
        "-n",
        "gradiated",
        "get",
        "pods",
        "-l",
        "app.kubernetes.io/name=worker",
        "-o",
        "json",
      ],
      undefined,
      signal,
    ),
  );
  const pod = pods.items.find(
    (item) =>
      !item.metadata.deletionTimestamp &&
      item.status.conditions?.some(
        (condition) =>
          condition.type === "Ready" && condition.status === "True",
      ),
  );
  if (!pod) throw new Error("No ready worker for production SDK verification");

  await execute(
    [
      "-n",
      "gradiated",
      "exec",
      "-i",
      pod.metadata.name,
      "--",
      "node",
      "services/worker/dist/verify-model.js",
    ],
    JSON.stringify(input),
    signal,
  );
  console.log(
    `${input.modelId}: production SDK passed (${input.deploymentId ?? "promoted routing"})`,
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
  const input = {
    modelId: job.Meta.gradiated_model_id,
    runtimeRevision: release.runtime_revision,
    ...(release.protocol ? { protocol: release.protocol } : {}),
  };
  const groups = job.TaskGroups.filter((group) => group.Count > 0);
  if (!groups.length) return undefined;
  if (
    groups.some(
      (group) =>
        group.Update?.HealthCheck !== "manual" ||
        !group.Update?.AutoPromote ||
        group.Update.Canary < group.Count,
    )
  )
    throw new Error(
      "SDK verification requires manual health and a full automatically promoted canary set",
    );

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

  return {
    qualify: async () => {
      const candidates = await allocations();
      if (!complete(candidates)) return;

      const pending = candidates.filter(
        (allocation) => allocation.DeploymentStatus?.Healthy !== true,
      );
      if (!pending.length) return;
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
        await Promise.all(
          pending.map((allocation) =>
            verify(
              {
                ...input,
                deploymentId: allocation.ID,
                deploymentIds: candidates.map((item) => item.ID),
              },
              signal,
            ),
          ),
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
    },
    finish: async () => {
      const promoted = await allocations();
      if (!complete(promoted))
        throw new Error("Promoted deployment is missing running allocations");
      await verify(
        {
          ...input,
          deploymentIds: promoted.map((allocation) => allocation.ID),
        },
        signal,
      );
    },
  };
};
