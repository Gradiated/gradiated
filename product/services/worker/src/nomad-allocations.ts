import { ModelDeploymentReleaseSchema } from "@gradiated/contracts";
import type { NomadAllocation } from "@gradiated/control";
import { z } from "zod";
export type NomadGet = (path: string) => Promise<unknown>;

const meta = z.record(z.string(), z.string()).nullish();
const jobsSchema = z.array(z.object({ ID: z.string(), Meta: meta }));
const allocationsSchema = z.array(
  z.object({
    ID: z.string(),
    NodeID: z.string(),
    ClientStatus: z.string(),
    DesiredStatus: z.string(),
    JobVersion: z.number().int(),
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

  const perJob = await Promise.all(
    jobs.map(async (job) => {
      const path = `/v1/job/${encodeURIComponent(job.ID)}`;
      const [allocations, versions] = await Promise.all([
        get(`${path}/allocations`).then((body) =>
          allocationsSchema.parse(body),
        ),
        get(`${path}/versions`).then((body) => versionsSchema.parse(body)),
      ]);
      const metaByVersion = new Map(
        versions.Versions.map((version) => [version.Version, version.Meta]),
      );

      const gated = versions.Versions.some(
        (version) => version.Meta?.gradiated_sdk_verification === "true",
      );
      const deployments = gated
        ? z
            .array(
              z.object({ JobVersion: z.number().int(), Status: z.string() }),
            )
            .parse((await get(`${path}/deployments`)) ?? [])
        : [];
      const unverified = new Set(
        deployments
          .filter((deployment) => deployment.Status !== "successful")
          .map((deployment) => deployment.JobVersion),
      );
      const updating = new Set(
        deployments
          .filter((deployment) => deployment.Status === "running")
          .map((deployment) => deployment.JobVersion),
      );

      return allocations
        .filter((allocation) => allocation.ClientStatus === "running")
        .flatMap((allocation) => {
          const versionMeta = metaByVersion.get(allocation.JobVersion);
          const modelId = versionMeta?.gradiated_model_id;
          const release = parseRelease(versionMeta?.gradiated_release);
          if (!modelId || !release.success) {
            onSkipped(allocation.ID, job.Meta?.gradiated_model_id ?? "");
            return [];
          }

          const qualifiedReplacement =
            updating.has(allocation.JobVersion) &&
            !allocation.DeploymentStatus?.Canary &&
            allocation.DeploymentStatus?.Healthy === true;

          return [
            {
              allocationId: allocation.ID,
              nodeId: allocation.NodeID,
              modelId,
              release: release.data,
              draining: allocation.DesiredStatus !== "run",
              ...(versionMeta?.gradiated_sdk_verification === "true" &&
              !qualifiedReplacement &&
              (allocation.DeploymentStatus?.Canary ||
                unverified.has(allocation.JobVersion))
                ? { verificationPending: true }
                : {}),
            },
          ];
        });
    }),
  );

  return perJob.flat();
};

const TERMINAL_STATUSES = new Set(["complete", "failed", "lost"]);
const allocationSchema = z.object({ ClientStatus: z.string() });

export const allocationIsGone = async (
  get: NomadGet,
  allocationId: string,
): Promise<boolean> => {
  try {
    const allocation = allocationSchema.parse(
      await get(`/v1/allocation/${encodeURIComponent(allocationId)}`),
    );
    return TERMINAL_STATUSES.has(allocation.ClientStatus);
  } catch (error) {
    if ((error as { code?: unknown }).code === "404") return true;
    throw error;
  }
};

export { createNomadRequest as createNomadGet } from "@gradiated/nomad-pki";
