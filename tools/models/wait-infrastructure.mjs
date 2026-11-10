import { execFileSync } from "node:child_process";
import { pathToFileURL } from "node:url";

const terraformPaths = [
  ".github/workflows/terraform.yml",
  "mise.toml",
  "infra/bootstrap/",
  "infra/modules/",
  "infra/environments/prod/us-east-1/terraform/",
  "tools/terraform/",
];

export const infrastructureRevision = (source, cwd = process.cwd()) => {
  if (!/^[0-9a-f]{40}$/.test(source)) {
    throw new Error("Expected a source commit revision");
  }

  return execFileSync(
    "git",
    [
      "log",
      "--first-parent",
      "-1",
      "--format=%H",
      source,
      "--",
      ...terraformPaths,
    ],
    { cwd, encoding: "utf8" },
  ).trim();
};

// A failed push apply can be repaired by a later manual apply on main; that
// apply covers the prerequisite when its commit contains it.
export const containsRevision = (revision, later, cwd = process.cwd()) => {
  try {
    execFileSync("git", ["merge-base", "--is-ancestor", revision, later], {
      cwd,
      stdio: "ignore",
    });
    return true;
  } catch {
    return false;
  }
};

export const waitForTerraform = async (
  revision,
  {
    fetchRuns,
    fetchLaterSuccesses = async () => [],
    contains = containsRevision,
    now = Date.now,
    wait = () => new Promise((resolve) => setTimeout(resolve, 15_000)),
  },
) => {
  const deadline = now() + 90 * 60 * 1000;

  while (true) {
    const runs = await fetchRuns(revision);
    const run = runs
      .filter((item) => item.head_sha === revision)
      .sort((a, b) => b.id - a.id)[0];
    if (run?.status === "completed") {
      if (run.conclusion !== "success") {
        const repaired = (await fetchLaterSuccesses()).find(
          (item) =>
            item.id > run.id &&
            item.conclusion === "success" &&
            contains(revision, item.head_sha),
        );
        if (!repaired) {
          throw new Error(`Terraform did not succeed: ${run.html_url}`);
        }
        console.log(
          `Terraform at ${revision} failed; a later apply covers it: ${repaired.html_url}`,
        );
      }

      return;
    }
    if (now() >= deadline) {
      throw new Error("Terraform did not finish within 90 minutes");
    }

    await wait();
  }
};

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  const {
    GITHUB_REPOSITORY: repository,
    GITHUB_TOKEN: token,
    SOURCE_SHA: source,
  } = process.env;
  const revision = infrastructureRevision(source);
  if (revision) {
    console.log(`Waiting for Terraform at prerequisite revision ${revision}.`);
    await waitForTerraform(revision, {
      fetchRuns: async (sha) => {
        const response = await fetch(
          `https://api.github.com/repos/${repository}/actions/workflows/terraform.yml/runs?event=push&head_sha=${sha}`,
          {
            headers: {
              Authorization: `Bearer ${token}`,
              Accept: "application/vnd.github+json",
            },
            signal: AbortSignal.timeout(30_000),
          },
        );
        if (!response.ok) {
          throw new Error(
            `Cannot read Terraform status: HTTP ${response.status}`,
          );
        }

        return (await response.json()).workflow_runs;
      },
      // Only push and manual runs on main apply; pull-request runs only plan.
      fetchLaterSuccesses: async () => {
        const runs = [];
        for (const event of ["push", "workflow_dispatch"]) {
          const response = await fetch(
            `https://api.github.com/repos/${repository}/actions/workflows/terraform.yml/runs?branch=main&event=${event}&status=success&per_page=20`,
            {
              headers: {
                Authorization: `Bearer ${token}`,
                Accept: "application/vnd.github+json",
              },
              signal: AbortSignal.timeout(30_000),
            },
          );
          if (!response.ok) {
            throw new Error(
              `Cannot read Terraform status: HTTP ${response.status}`,
            );
          }
          runs.push(...(await response.json()).workflow_runs);
        }

        return runs.filter((item) => item.head_branch === "main");
      },
    });
    console.log("Terraform succeeded. Deployment can proceed.");
  }
}
