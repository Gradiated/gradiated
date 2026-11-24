import { execFileSync, spawnSync } from "node:child_process";
import { appendFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

const metadata =
  "infra/environments/prod/us-east-1/kubernetes/workloads/release-metadata.yaml";

export const releaseOrder = (
  source,
  root = process.cwd(),
  releaseStateRoot = root,
) => {
  if (!/^[0-9a-f]{40}$/.test(source)) throw new Error("Invalid source SHA");

  const ancestor = (before, after) => {
    const result = spawnSync(
      "git",
      ["merge-base", "--is-ancestor", before, after],
      { cwd: root, stdio: "pipe" },
    );
    if (result.status !== 0 && result.status !== 1)
      throw new Error("Cannot determine release ancestry");

    return result.status === 0;
  };
  if (!ancestor(source, "origin/main"))
    throw new Error("Release source is not on main");

  let contents;
  for (const candidate of [
    "environments/prod/us-east-1/kubernetes/workloads/release-metadata.yaml",
    metadata,
  ]) {
    try {
      contents = execFileSync("git", ["show", `origin/main:${candidate}`], {
        cwd: releaseStateRoot,
        encoding: "utf8",
        stdio: ["ignore", "pipe", "ignore"],
      });
      break;
    } catch {}
  }
  if (contents === undefined)
    throw new Error(`Missing ${metadata} on origin/main`);
  const current = contents.match(/^  sourceRevision: "([^"]+)"$/m)?.[1];
  if (current === "unreleased" || current === source)
    return { deploy: true, current };
  if (!/^[0-9a-f]{40}$/.test(current ?? ""))
    throw new Error("Invalid recorded release source");
  if (ancestor(source, current)) return { deploy: false, current };
  if (!ancestor(current, source))
    throw new Error("Release source diverges from the recorded release");

  return { deploy: true, current };
};

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  const result = releaseOrder(
    process.argv[2],
    process.cwd(),
    process.env.RELEASE_STATE_ROOT || undefined,
  );
  if (!result.deploy && process.argv.includes("--reject-stale"))
    throw new Error("A newer release was recorded while this workflow ran");
  if (process.env.GITHUB_OUTPUT)
    appendFileSync(process.env.GITHUB_OUTPUT, `deploy=${result.deploy}\n`);
  console.log(
    result.deploy
      ? "Release source is current or newer"
      : `Skipping stale source; ${result.current} is already recorded`,
  );
}
