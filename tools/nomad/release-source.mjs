import { execFileSync, spawnSync } from "node:child_process";
import { pathToFileURL } from "node:url";
import { catalog } from "../images/catalog.mjs";
import { bundles } from "../models/release.mjs";

const inputs = [
  ...new Set([
    ...catalog["nomad-base"].paths,
    ...Object.values(bundles).flat(),
    "product/inference/bundles/package.sh",
    "product/inference/nomad/jobs/",
    "tools/nomad/",
    "tools/models/",
    "tools/images/",
    ".github/workflows/nomad-deployment.yml",
    ".github/workflows/model-deployment.yml",
    ".github/workflows/build-images.yml",
  ]),
];

export const assertReleaseSource = (source, root = process.cwd()) => {
  if (!/^[0-9a-f]{40}$/.test(source)) throw new Error("Invalid source SHA");
  const ancestor = spawnSync(
    "git",
    ["merge-base", "--is-ancestor", source, "origin/main"],
    { cwd: root },
  );
  if (ancestor.status !== 0)
    throw new Error("Deployment source is not a verified ancestor of main");

  const tree = (revision) =>
    execFileSync("git", ["ls-tree", "-r", "-z", revision, "--", ...inputs], {
      cwd: root,
    });
  if (!tree(source).equals(tree("origin/main")))
    throw new Error(
      "Main has newer model deployment inputs; refusing a stale rollout. Deploy current main or merge a Git revert.",
    );
};

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  assertReleaseSource(process.argv[2]);
  console.log("Model deployment inputs match current main");
}
