import { execFileSync } from "node:child_process";
import { appendFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { catalog } from "../images/catalog.mjs";
import { matches } from "../images/images.mjs";
import { bundles } from "./release.mjs";

const everyBundleInputs = [
  "product/inference/.dockerignore",
  "product/inference/bundles/build.hcl",
  "product/inference/bundles/package.sh",
  ".github/workflows/model-deployment.yml",
  "tools/models/verify-inputs.mjs",
];
const affectsEveryBundle = (path) =>
  matches(path, catalog["gpu-base"].paths) || everyBundleInputs.includes(path);
const within = (path, input) => path === input || path.startsWith(`${input}/`);

// Compare the full PR against its base. Comparing only the last push could skip
// an earlier runtime change whose verification failed or was cancelled.
export const bundlesToVerify = (paths) => {
  const relevant = paths.filter((path) => !path.endsWith(".md"));
  return Object.keys(bundles).filter((bundle) =>
    relevant.some(
      (path) =>
        affectsEveryBundle(path) ||
        bundles[bundle].some((input) => within(path, input)),
    ),
  );
};

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  const base = process.argv[2];
  if (!/^[0-9a-f]{40}$/.test(base))
    throw new Error("Expected the full PR base SHA");
  const paths = execFileSync(
    "git",
    ["diff", "--name-only", "-z", `${base}...HEAD`],
    { encoding: "utf8" },
  )
    .split("\0")
    .filter(Boolean);
  const verify = bundlesToVerify(paths);
  appendFileSync(
    process.env.GITHUB_OUTPUT,
    `required=${verify.length > 0}\ntargets=${verify.map((bundle) => `verify-${bundle}`).join(",")}\n`,
  );
}
