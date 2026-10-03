import { waitForVerificationInfrastructure } from "./verification-infrastructure.mjs";
import { validateModelRollout, verifyInProduction } from "./verification.mjs";
import { readFileSync } from "node:fs";
import { setTimeout as delay } from "node:timers/promises";
import { pathToFileURL } from "node:url";
import { createNomadClient } from "./api.mjs";
import {
  replicaJobs,
  releaseFailedMigration,
  retireLegacyReplica,
  withPeerHostConstraints,
  validateReplicaRetirement,
} from "./replica-jobs.mjs";
import { waitForDeployment, waitForEvaluation } from "./wait-deployments.mjs";

const latestDeployment = async (job, get) => {
  const deployments =
    (await get(`/v1/job/${encodeURIComponent(job)}/deployments`)) ?? [];
  return deployments.sort((a, b) => b.CreateIndex - a.CreateIndex)[0];
};

export const submitJob = async (
  job,
  {
    get,
    post,
    signal,
    verify,
    prepare = async (job) => job,
    pause = (ms) => delay(ms, undefined, { signal }),
  },
) => {
  validateModelRollout(job);

  const path = `/v1/job/${encodeURIComponent(job.ID)}`;
  while (!signal.aborted) {
    const prepared = await prepare(job);
    const plan = await post(`${path}/plan`, { Job: prepared, Diff: true });
    const prior = plan.JobModifyIndex
      ? await latestDeployment(job.ID, get)
      : undefined;
    if (plan.Diff?.Type === "None") {
      const disabled = job.TaskGroups?.every((group) => group.Count === 0);
      if (
        !disabled &&
        prior &&
        !["pending", "running", "paused", "successful"].includes(prior.Status)
      )
        throw new Error(
          `${job.ID}: unchanged deployment ${prior.ID} is ${prior.Status}`,
        );
      if (
        !disabled &&
        !prior &&
        job.Meta?.gradiated_sdk_verification === "true"
      )
        throw new Error(
          `${job.ID}: unchanged model has no qualified deployment`,
        );
      return { deployment: disabled ? undefined : prior?.ID };
    }
    if (
      !plan.Diff ||
      !["Added", "Edited", "Deleted"].includes(plan.Diff.Type)
    ) {
      throw new Error(`Unrecognized plan for ${job.ID}`);
    }

    const groups = Object.values(prior?.TaskGroups ?? {});
    const unplaced =
      prior?.Status !== "paused" &&
      groups.length > 0 &&
      groups.every((group) => group.PlacedAllocs === 0);
    if (
      prior &&
      ["pending", "running", "paused"].includes(prior.Status) &&
      !unplaced
    ) {
      if (verify)
        await waitForDeployment(prior.ID, { get, post, signal, verify, pause });
      else await pause(10_000);
      continue;
    }
    {
      const allocations = (await get("/v1/allocations")) ?? [];
      if (
        allocations.some(
          (allocation) =>
            allocation.DesiredStatus === "stop" &&
            !["complete", "failed", "lost", "unknown"].includes(
              allocation.ClientStatus,
            ),
        )
      ) {
        await pause(10_000);
        continue;
      }
    }

    const result = await post("/v1/jobs", {
      Job: prepared,
      EnforceIndex: true,
      JobModifyIndex: plan.JobModifyIndex,
    });
    if (!result.EvalID)
      throw new Error(`Registration omitted evaluation for ${job.ID}`);
    return { evaluation: result.EvalID, previous: prior?.ID ?? "" };
  }
  throw new Error(
    `Prior rollout or drain for ${job.ID} did not finish before its deadline`,
  );
};

export const deployJobs = async (jobs, deploy) => {
  const errors = new Map();
  const attempt = async (job) => {
    try {
      await deploy(job);
      return true;
    } catch (error) {
      errors.set(job.ID, error?.message ?? "deployment failed");
      return false;
    }
  };
  const models = async () => {
    const failed = new Set();
    for (const job of jobs.filter((job) => job.Meta?.gradiated_model_id)) {
      const model = job.Meta.gradiated_model_id;
      if (!failed.has(model) && !(await attempt(job))) failed.add(model);
    }
  };
  await Promise.all([
    models(),
    ...jobs.filter((job) => !job.Meta?.gradiated_model_id).map(attempt),
  ]);
  const failures = jobs.flatMap((job) =>
    errors.has(job.ID) ? [`${job.ID}: ${errors.get(job.ID)}`] : [],
  );

  if (failures.length) throw new Error(failures.join("\n"));
};

const main = async () => {
  const sources = JSON.parse(readFileSync(process.argv[2], "utf8"));
  const jobs = replicaJobs(sources);
  const controller = new AbortController();
  const client = createNomadClient(controller.signal);
  try {
    await validateReplicaRetirement(sources, client);
    if (
      jobs.some(
        (job) =>
          job.Meta?.gradiated_sdk_verification === "true" &&
          job.TaskGroups.some((group) => group.Count > 0),
      )
    ) {
      console.log(
        "Waiting for the Git-defined verification workloads and CI authorization before registering model jobs",
      );
      await waitForVerificationInfrastructure(
        AbortSignal.any([controller.signal, AbortSignal.timeout(15 * 60_000)]),
      );
    }
    await deployJobs(jobs, async (job) => {
      console.log(
        `${job.ID}: planning without interrupting existing canaries or draining requests`,
      );
      const options = {
        ...client,
        verify: verifyInProduction,
        prepare: (source) => withPeerHostConstraints(source, client),
        signal: AbortSignal.any([
          controller.signal,
          AbortSignal.timeout(
            Math.max(
              ...job.TaskGroups.map((group) =>
                group.Update?.ProgressDeadline
                  ? group.Update.ProgressDeadline / 1_000_000 + 5 * 60_000
                  : 110 * 60_000,
              ),
            ),
          ),
        ]),
      };
      try {
        const registration = await submitJob(job, options);
        if (registration.deployment) {
          console.log(
            `${job.ID}: unchanged; following deployment ${registration.deployment}`,
          );
          await waitForDeployment(registration.deployment, options);
        } else if (registration.evaluation) {
          console.log(
            `${job.ID}: following evaluation ${registration.evaluation}`,
          );
          await waitForEvaluation(
            registration.evaluation,
            registration.previous,
            options,
          );
        }
        await retireLegacyReplica(job, options);
      } catch (error) {
        try {
          await releaseFailedMigration(job, options);
        } catch (cleanupError) {
          console.error(
            `${job.ID}: staging cleanup failed: ${cleanupError.message}`,
          );
        }
        throw error;
      }
      console.log(`${job.ID}: deployment healthy or no deployment required`);
    });
  } finally {
    controller.abort();
  }
};

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  main().catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
}
