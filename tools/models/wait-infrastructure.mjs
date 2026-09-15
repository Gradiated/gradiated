import { execFileSync } from "node:child_process";

const {
  GITHUB_REPOSITORY: repository,
  GITHUB_TOKEN: token,
  SOURCE_SHA: source,
  BEFORE_SHA: before,
} = process.env;
if (!/^[0-9a-f]{40}$/.test(source) || !/^[0-9a-f]{40}$/.test(before)) {
  throw new Error("Expected push commit revisions");
}
const files = execFileSync("git", ["diff", "--name-only", before, source], {
  encoding: "utf8",
}).split("\n");
const needsTerraform = files.some(
  (file) =>
    file === ".github/workflows/terraform.yml" ||
    file === "mise.toml" ||
    [
      "infra/bootstrap/",
      "infra/modules/",
      "infra/environments/prod/us-east-1/terraform/",
    ].some((prefix) => file.startsWith(prefix)),
);
if (needsTerraform) {
  const deadline = Date.now() + 90 * 60 * 1000;
  console.log("Waiting for the Terraform workflow for this source revision.");
  while (true) {
    const response = await fetch(
      `https://api.github.com/repos/${repository}/actions/workflows/terraform.yml/runs?event=push&head_sha=${source}`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: "application/vnd.github+json",
        },
        signal: AbortSignal.timeout(30_000),
      },
    );
    if (!response.ok)
      throw new Error(`Cannot read Terraform status: HTTP ${response.status}`);
    const { workflow_runs: runs } = await response.json();
    const run = runs
      .filter((item) => item.head_sha === source)
      .sort((a, b) => b.id - a.id)[0];
    if (run?.status === "completed") {
      if (run.conclusion !== "success")
        throw new Error(`Terraform did not succeed: ${run.html_url}`);
      console.log("Terraform succeeded. Runtime publication can proceed.");
      break;
    }
    if (Date.now() >= deadline)
      throw new Error("Terraform did not finish within 90 minutes");
    await new Promise((resolve) => setTimeout(resolve, 15_000));
  }
}
