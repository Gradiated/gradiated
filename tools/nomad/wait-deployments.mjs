import { createVerificationGate } from "./verification.mjs";
import { readFileSync } from "node:fs";
import { createNomadClient } from "./api.mjs";
import { setTimeout as delay } from "node:timers/promises";
import { pathToFileURL } from "node:url";

export const waitForDeployment = async (id, options) => {
  const {
    get,
    signal,
    verify,
    pause = (ms) => delay(ms, undefined, { signal }),
  } = options;
  let gate;
  let initialized = false;
  while (!signal.aborted) {
    const deployment = await get(
      `/v1/deployment/${encodeURIComponent(id)}`,
      signal,
    );
    if (verify && !initialized) {
      gate = await createVerificationGate(deployment, options);
      initialized = true;
    }
    if (deployment.Status === "successful") {
      await gate?.finish();
      return;
    }
    if (["failed", "cancelled", "blocked"].includes(deployment.Status)) {
      throw new Error(`Deployment ${id} is ${deployment.Status}`);
    }
    await gate?.qualify();
    await pause(10_000);
  }
  throw new Error(
    `Deployment ${id} did not become healthy before its deadline`,
  );
};

export const waitForEvaluation = async (id, previous, options) => {
  const {
    get,
    signal,
    pause = (ms) => delay(ms, undefined, { signal }),
  } = options;
  while (!signal.aborted) {
    const evaluation = await get(
      `/v1/evaluation/${encodeURIComponent(id)}`,
      signal,
    );
    if (["failed", "cancelled"].includes(evaluation.Status))
      throw new Error(`Evaluation ${id} is ${evaluation.Status}`);
    if (evaluation.Status === "complete") {
      if (evaluation.DeploymentID && evaluation.DeploymentID !== previous) {
        await waitForDeployment(evaluation.DeploymentID, options);
      }
      return;
    }
    await pause(1_000);
  }
  throw new Error(`Evaluation ${id} did not complete before its deadline`);
};

export { renewingToken } from "./api.mjs";

const main = async () => {
  const deployments = JSON.parse(readFileSync(process.argv[2], "utf8"));
  const controller = new AbortController();
  const signal = AbortSignal.any([
    controller.signal,
    AbortSignal.timeout(110 * 60_000),
  ]);
  const { get } = createNomadClient(signal);
  try {
    await Promise.all(
      deployments.map(async ({ job, evaluation, previous }) => {
        console.log(
          `Waiting for ${job} evaluation ${evaluation} and any new deployment`,
        );
        await waitForEvaluation(evaluation, previous, { get, signal });
        console.log(
          `${job}: evaluation complete; any new deployment is healthy`,
        );
      }),
    );
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
