import { execFileSync } from "node:child_process";
import { appendFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { plan } from "../images/images.mjs";
import { consoleKey } from "./console-artifact.mjs";

const metadataPath =
  "infra/environments/prod/us-east-1/kubernetes/workloads/release-metadata.yaml";
const backendManifests = [
  "infra/environments/prod/us-east-1/kubernetes/workloads",
  "infra/environments/prod/us-east-1/kubernetes/gpu-inference/controller.yaml",
  "infra/environments/prod/us-east-1/kubernetes/gpu-inference/gpu-fleet.yaml",
  "infra/environments/prod/us-east-1/kubernetes/operations/ops-mcp",
];
export const backendManifestChanges = (before, after) => {
  // Generated release commits rewrite image pins. Counting those as source
  // changes would make every later console-only release wait for the backend.
  const subjects = execFileSync(
    "git",
    ["log", "--format=%s", `${before}..${after}`, "--", ...backendManifests],
    { encoding: "utf8" },
  ).trim();
  return subjects
    .split("\n")
    .some(
      (subject) =>
        subject &&
        !/^deploy\(prod\): release [a-f0-9]{12} \[skip ci\]$/.test(subject),
    );
};
const images = ["product", "gateway", "proxy", "collector", "gpu-controller"];
export const releasePlan = (
  source,
  metadata,
  readImages,
  diffConsole,
  diffManifests = () => false,
) => {
  const previous = metadata.match(/^  sourceRevision: "([a-f0-9]{40})"$/m)?.[1];
  const priorConsole = metadata.match(
    /^  consoleRevision: "([a-f0-9]{40})"$/m,
  )?.[1];
  if (!previous) return { backend: true, console: true, console_sha: source };
  const before = readImages(previous);
  const after = readImages(source);
  const backend =
    after.some((image, index) => image.tag !== before[index].tag) ||
    diffManifests(previous, source);
  const console = diffConsole(previous, source);
  return {
    backend,
    console,
    console_sha: console ? source : (priorConsole ?? previous),
  };
};
export const deploymentRuns = async (metadata, previous, api) => {
  const recorded = metadata.match(
    /^  deploymentRunId: "([1-9][0-9]{0,19})"$/m,
  )?.[1];
  if (recorded) {
    const run = await api(`actions/runs/${recorded}`);
    if (run.path !== ".github/workflows/application-deployment.yml")
      throw new Error("Recorded run is not an application deployment");
    return [run];
  }
  // Compatibility with releases recorded before deploymentRunId existed.
  return (
    await api(
      `actions/workflows/application-deployment.yml/runs?head_sha=${previous}&per_page=100`,
    )
  ).workflow_runs;
};
export const applyDispatch = (result, source, event) =>
  event === "workflow_dispatch"
    ? {
        ...result,
        console: true,
        console_sha: source,
      }
    : result;
// Release metadata precedes rollout and publication. Retry the components that
// remained incomplete, preserving an unchanged console after a backend failure.
export const requireVerifiedPrevious = (
  result,
  source,
  verified,
  jobs = [],
) => {
  if (verified) return result;
  const stage = jobs.find((job) => job.name === "Stage verified console");
  const rollout = jobs.find((job) => job.name === "Wait for Argo rollout");
  const publish = jobs.find(
    (job) => job.name === "Publish console and verify production",
  );
  if (!stage || !rollout)
    throw new Error("Cannot establish incomplete release components");
  const pendingConsole =
    stage.conclusion === "success" && publish?.conclusion !== "success";
  return {
    ...result,
    backend:
      result.backend || !["success", "skipped"].includes(rollout.conclusion),
    console: result.console || pendingConsole,
    console_sha: result.console || pendingConsole ? source : result.console_sha,
  };
};

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  const source = process.argv[2];
  if (!/^[a-f0-9]{40}$/.test(source)) throw new Error("Invalid source SHA");
  const metadata = execFileSync(
    "git",
    ["show", `origin/main:${metadataPath}`],
    { encoding: "utf8" },
  );
  let result = releasePlan(
    source,
    metadata,
    (revision) => plan(images, revision).include,
    (before, after) => consoleKey(before) !== consoleKey(after),
    backendManifestChanges,
  );
  if (!result.backend || !result.console) {
    const previous = metadata.match(
      /^  sourceRevision: "([a-f0-9]{40})"$/m,
    )?.[1];
    const api = async (path) => {
      const response = await fetch(
        `https://api.github.com/repos/${process.env.GITHUB_REPOSITORY}/${path}`,
        {
          headers: {
            Authorization: `Bearer ${process.env.GITHUB_TOKEN}`,
            Accept: "application/vnd.github+json",
          },
          signal: AbortSignal.timeout(20000),
        },
      );
      if (!response.ok)
        throw new Error("Cannot establish the last deployment state");
      return response.json();
    };
    const runs = await deploymentRuns(metadata, previous, api);
    const verified = runs.some(
      (run) => run.status === "completed" && run.conclusion === "success",
    );
    let recordedJobs;
    if (!verified) {
      for (const run of runs) {
        const { jobs } = await api(`actions/runs/${run.id}/jobs?per_page=100`);
        if (
          jobs.some(
            (job) =>
              job.name === "Record immutable release" &&
              job.conclusion === "success",
          )
        ) {
          recordedJobs = jobs;
          break;
        }
      }
    }
    result = requireVerifiedPrevious(result, source, verified, recordedJobs);
  }

  result = applyDispatch(result, source, process.env.EVENT);
  for (const [key, value] of Object.entries(result))
    appendFileSync(process.env.GITHUB_OUTPUT, `${key}=${value}\n`);
}
