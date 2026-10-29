import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import {
  appendFile,
  lstat,
  mkdir,
  readFile,
  readdir,
  writeFile,
} from "node:fs/promises";
import { pathToFileURL } from "node:url";
import { findArtifact } from "../images/verified.mjs";
const inputs = [
  "product/services/console",
  "product/packages/contracts",
  "product/packages/analytics",
  "product/package.json",
  "product/pnpm-lock.yaml",
  "product/pnpm-workspace.yaml",
  "product/tsconfig.base.json",
  "product/turbo.json",
  "product/.nvmrc",
  "mise.toml",
  "tools/deployment/console-artifact.mjs",
  ".github/workflows/tests.yml",
];
export const consoleKey = (revision, environment = process.env) =>
  createHash("sha256")
    .update(
      execFileSync("git", ["ls-tree", "-r", "-z", revision, "--", ...inputs], {
        encoding: "utf8",
      })
        .split("\0")
        .filter((entry) => {
          const path = entry.split("\t")[1];
          return (
            path && !path.includes("/screenshots/") && !path.endsWith(".md")
          );
        })
        .join("\0"),
    )
    .update(
      JSON.stringify([environment.VITE_API_URL, environment.VITE_POSTHOG_KEY]),
    )
    .digest("hex");
export const fileHashes = async (directory, prefix = "") => {
  const result = {};
  for (const entry of (await readdir(directory)).sort()) {
    if (!prefix && entry === "console-proof.json") continue;
    const relative = prefix + entry;
    const path = `${directory}/${entry}`;
    const stat = await lstat(path);
    if (stat.isSymbolicLink())
      throw new Error("Console artifact cannot contain symbolic links");
    if (stat.isDirectory())
      Object.assign(result, await fileHashes(path, relative + "/"));
    else
      result[relative] = createHash("sha256")
        .update(await readFile(path))
        .digest("hex");
  }
  return result;
};
export const validateConsole = async (directory, key) => {
  const proof = JSON.parse(
    await readFile(`${directory}/console-proof.json`, "utf8"),
  );
  if (
    proof.schema !== 1 ||
    proof.key !== key ||
    JSON.stringify(proof.files) !== JSON.stringify(await fileHashes(directory))
  )
    throw new Error("Console artifact input identity or integrity mismatch");
  await readFile(`${directory}/index.html`);
};
const main = async () => {
  const [command, revision, directory = "product/services/console/dist"] =
    process.argv.slice(2);
  const key = consoleKey(revision);
  const name = `ci-console-${key}`;
  const output = (key, value) =>
    appendFile(process.env.GITHUB_OUTPUT, `${key}=${value}\n`);
  await output("artifact", name);
  if (command === "record") {
    await writeFile(
      `${directory}/console-proof.json`,
      JSON.stringify({ schema: 1, key, files: await fileHashes(directory) }),
    );
    return;
  }
  if (!["find", "fetch"].includes(command))
    throw new Error("Unknown console artifact command");
  const artifact = await findArtifact(name, command === "find");
  await output("reused", String(Boolean(artifact)));
  if (command === "find") return;
  if (!artifact)
    throw new Error(
      "No passing CI console artifact matches this release and its public build configuration. Rebase/retest the PR.",
    );
  await mkdir(directory, { recursive: true });
  execFileSync(
    "gh",
    [
      "run",
      "download",
      String(artifact.workflow_run.id),
      "--repo",
      process.env.GITHUB_REPOSITORY,
      "--name",
      name,
      "--dir",
      directory,
    ],
    { stdio: "inherit" },
  );
  await validateConsole(directory, key);
};
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href)
  await main();
