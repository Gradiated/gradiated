import { verifyInProduction } from "./verification.mjs";
import { readFileSync } from "node:fs";
import { setTimeout as delay } from "node:timers/promises";
import { pathToFileURL } from "node:url";
import { createNomadClient } from "./api.mjs";
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
    pause = (ms) => delay(ms, undefined, { signal }),
  },
) => {
  const path = `/v1/job/${encodeURIComponent(job.ID)}`;
  while (!signal.aborted) {
    const plan = await post(`${path}/plan`, { Job: job, Diff: true });
    const prior = plan.JobModifyIndex
      ? await latestDeployment(job.ID, get)
      : undefined;
    if (plan.Diff?.Type === "None") {
      return {
        deployment:
          prior && ["pending", "running", "paused"].includes(prior.Status)
            ? prior.ID
            : undefined,
      };
    }
    if (
      !plan.Diff ||
      !["Added", "Edited", "Deleted"].includes(plan.Diff.Type)
    ) {
      throw new Error(`Unrecognized plan for ${job.ID}`);
    }

    if (prior && ["pending", "running", "paused"].includes(prior.Status)) {
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
      Job: job,
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
  const results = await Promise.allSettled(
    jobs.map(async (job) => deploy(job)),
  );
  const failures = results.flatMap((result, index) =>
    result.status === "rejected"
      ? [`${jobs[index].ID}: ${result.reason?.message ?? "deployment failed"}`]
      : [],
  );

  if (failures.length) throw new Error(failures.join("\n"));
};

const main = async () => {
  const jobs = JSON.parse(readFileSync(process.argv[2], "utf8"));
  const controller = new AbortController();
  const client = createNomadClient(controller.signal);
  try {
    await deployJobs(jobs, async (job) => {
      console.log(
        `${job.ID}: planning without interrupting existing canaries or draining requests`,
      );
      const registration = await submitJob(job, {
        ...client,
        verify: verifyInProduction,
        signal: AbortSignal.any([
          controller.signal,
          AbortSignal.timeout(110 * 60_000),
        ]),
      });
      const options = {
        ...client,
        verify: verifyInProduction,
        signal: AbortSignal.any([
          controller.signal,
          AbortSignal.timeout(110 * 60_000),
        ]),
      };
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
