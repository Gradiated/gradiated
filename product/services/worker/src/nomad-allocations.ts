import { ModelDeploymentReleaseSchema } from "@gradiated/contracts";
import type { NomadAllocation } from "@gradiated/control";
import { z } from "zod";
export type NomadGet = (path: string) => Promise<unknown>;

const meta = z.record(z.string(), z.string()).nullish();
const jobsSchema = z.array(z.object({ ID: z.string(), Meta: meta }));
const allocationsSchema = z.array(
  z.object({
    ID: z.string(),
    Name: z.string().optional(),
    NodeID: z.string(),
    ClientStatus: z.string(),
    DesiredStatus: z.string(),
    JobVersion: z.number().int(),
    CreateIndex: z.number().int().optional(),
    DeploymentStatus: z
      .object({
        Canary: z.boolean().optional(),
        Healthy: z.boolean().nullish(),
      })
      .nullish(),
  }),
);
const versionsSchema = z.object({
  Versions: z.array(z.object({ Version: z.number().int(), Meta: meta })),
});

const parseRelease = (value: string | undefined) => {
  try {
    return ModelDeploymentReleaseSchema.safeParse(JSON.parse(value ?? ""));
  } catch {
    return { success: false as const };
  }
};

// Model jobs carry meta.gradiated_model_id and a JSON meta.gradiated_release. The
// release comes from each allocation's own job version so a rollout stays correct.
export const readModelAllocations = async (
  get: NomadGet,
  onSkipped: (allocationId: string, modelId: string) => void,
): Promise<NomadAllocation[]> => {
  const jobs = jobsSchema
    .parse(await get("/v1/jobs?meta=true"))
    .filter((job) => job.Meta?.gradiated_model_id);
  const parents = new Set(
    jobs.flatMap((job) =>
      job.Meta?.gradiated_replica_parent
        ? [job.Meta.gradiated_replica_parent]
        : [],
    ),
  );

  const perJob = await Promise.all(
    jobs.map(async (job) => {
      const path = `/v1/job/${encodeURIComponent(job.ID)}`;
      const allocations = allocationsSchema.parse(
        await get(`${path}/allocations`),
      );
      const versions = versionsSchema.parse(await get(`${path}/versions`));
      const metaByVersion = new Map(
        versions.Versions.map((version) => [version.Version, version.Meta]),
      );

      const gated = versions.Versions.some(
        (version) => version.Meta?.gradiated_sdk_verification === "true",
      );
      const deployments = gated
        ? z
            .array(
              z.object({
                JobVersion: z.number().int(),
                Status: z.string(),
                CreateIndex: z.number().int().optional(),
              }),
            )
            .parse((await get(`${path}/deployments`)) ?? [])
        : [];
      const unverified = new Set(
        deployments
          .filter((deployment) => deployment.Status !== "successful")
          .map((deployment) => deployment.JobVersion),
      );
      const rejected = new Set(
        deployments
          .filter((deployment) =>
            ["failed", "cancelled", "blocked"].includes(deployment.Status),
          )
          .map((deployment) => deployment.JobVersion),
      );
      const updating = new Set(
        deployments
          .filter((deployment) => deployment.Status === "running")
          .map((deployment) => deployment.JobVersion),
      );

      const failed = deployments
        .filter((deployment) => deployment.Status === "failed")
        .sort((a, b) => b.JobVersion - a.JobVersion)[0];
      const verifiedReleases = new Set(
        deployments
          .filter(
            (deployment) =>
              deployment.Status === "successful" &&
              metaByVersion.get(deployment.JobVersion)
                ?.gradiated_sdk_verification === "true",
          )
          .map(
            (deployment) =>
              metaByVersion.get(deployment.JobVersion)?.gradiated_release,
          )
          .filter((release): release is string => release !== undefined),
      );

      return allocations
        .filter(
          (allocation) =>
            !["complete", "failed", "lost"].includes(allocation.ClientStatus),
        )
        .flatMap((allocation) => {
          const versionMeta = metaByVersion.get(allocation.JobVersion);
          const modelId = versionMeta?.gradiated_model_id;
          const release = parseRelease(versionMeta?.gradiated_release);
          if (!modelId || !release.success) {
            onSkipped(allocation.ID, job.Meta?.gradiated_model_id ?? "");
            return [];
          }

          const parent = job.Meta?.gradiated_replica_parent;
          // Rollback can rebind a retained allocation and clear its manual health.
          // Its identity predates the failed rollout and its release already passed SDK checks.
          const retainedRollback =
            failed?.CreateIndex !== undefined &&
            allocation.CreateIndex !== undefined &&
            allocation.CreateIndex < failed.CreateIndex &&
            allocation.JobVersion > failed.JobVersion &&
            !allocation.DeploymentStatus?.Canary &&
            versionMeta?.gradiated_release !== undefined &&
            verifiedReleases.has(versionMeta.gradiated_release);
          const qualifiedReplacement =
            retainedRollback ||
            (updating.has(allocation.JobVersion) &&
              (!allocation.DeploymentStatus?.Canary || parent) &&
              allocation.DeploymentStatus?.Healthy === true);
          const family = parent ?? (parents.has(job.ID) ? job.ID : undefined);
          const slot = parent
            ? job.Meta?.gradiated_replica_slot
            : allocation.Name?.match(/\[(\d+)\]$/)?.[1];
          if (family && (!slot || !/^\d+$/.test(slot))) {
            onSkipped(allocation.ID, modelId);
            return [];
          }

          return [
            {
              allocationId: allocation.ID,
              nodeId: allocation.NodeID,
              modelId,
              release: release.data,
              draining: allocation.DesiredStatus !== "run",
              replicaKey: family ? `${modelId}:${family}:${slot}` : undefined,
              replicaChild: Boolean(parent),
              replicaOrder: allocation.CreateIndex ?? allocation.JobVersion,
              replicaRejected: rejected.has(allocation.JobVersion),
              ...(allocation.ClientStatus !== "running" ||
              (versionMeta?.gradiated_sdk_verification === "true" &&
                !qualifiedReplacement &&
                (allocation.DeploymentStatus?.Canary ||
                  unverified.has(allocation.JobVersion)))
                ? { verificationPending: true }
                : {}),
            },
          ];
        });
    }),
  );

  const allocations = perJob.flat();
  const selected = new Map<string, (typeof allocations)[number]>();
  for (const allocation of allocations) {
    if (
      !allocation.replicaKey ||
      allocation.draining ||
      allocation.verificationPending
    )
      continue;
    const previous = selected.get(allocation.replicaKey);
    if (
      !previous ||
      Number(allocation.replicaChild) > Number(previous.replicaChild) ||
      (allocation.replicaChild === previous.replicaChild &&
        allocation.replicaOrder > previous.replicaOrder)
    )
      selected.set(allocation.replicaKey, allocation);
  }
  return allocations.map(
    ({
      replicaKey,
      replicaChild,
      replicaOrder,
      replicaRejected,
      ...allocation
    }) => ({
      ...allocation,
      ...(replicaKey
        ? {
            replica: {
              key: replicaKey,
              child: replicaChild,
              order: replicaOrder,
            },
          }
        : {}),
      draining:
        allocation.draining ||
        Boolean(
          replicaKey &&
          selected.has(replicaKey) &&
          selected.get(replicaKey)!.allocationId !== allocation.allocationId &&
          (replicaRejected ||
            Number(selected.get(replicaKey)!.replicaChild) >
              Number(replicaChild) ||
            (selected.get(replicaKey)!.replicaChild === replicaChild &&
              selected.get(replicaKey)!.replicaOrder >= replicaOrder)),
        ),
    }),
  );
};

const TERMINAL_STATUSES = new Set(["complete", "failed", "lost"]);
const allocationSchema = z.object({
  ClientStatus: z.string(),
  DesiredStatus: z.string().optional(),
});

export const allocationIsGone = async (
  get: NomadGet,
  allocationId: string,
): Promise<boolean> => {
  try {
    const allocation = allocationSchema.parse(
      await get(`/v1/allocation/${encodeURIComponent(allocationId)}`),
    );
    return (
      TERMINAL_STATUSES.has(allocation.ClientStatus) ||
      allocation.DesiredStatus === "stop"
    );
  } catch (error) {
    if ((error as { code?: unknown }).code === "404") return true;
    throw error;
  }
};

export { createNomadRequest as createNomadGet } from "@gradiated/nomad-pki";
