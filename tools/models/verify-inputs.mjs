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
const workflowPath = ".github/workflows/model-deployment.yml";

export const workflowRequiresVerification = (before, after) => {
  const triggers = /^on:\n(?:[ \t]+[^\n]*\n|\n)*/m;
  if (!triggers.test(before) || !triggers.test(after)) return true;
  if (before.replace(triggers, "") !== after.replace(triggers, "")) return true;
  try {
    // Anchors can make trigger edits change jobs outside the trigger block.
    execFileSync("python3", ["-c", `
import json, sys, yaml
for text in json.load(sys.stdin):
    yaml.load(text, Loader=yaml.BaseLoader)
    if any(isinstance(token, (yaml.tokens.AnchorToken, yaml.tokens.AliasToken)) for token in yaml.scan(text)):
        raise ValueError('Workflow contains anchors or aliases')
`], { input: JSON.stringify([before, after]), stdio: ["pipe", "pipe", "pipe"] });
    return false;
  } catch {
    return true;
  }
};

// Compare the full PR against its base. Comparing only the last push could skip
// an earlier runtime change whose verification failed or was cancelled.
export const bundlesToVerify = (paths, { triggerOnly = false } = {}) => {
  const relevant = paths.filter(
    (path) => !path.endsWith(".md") && !(triggerOnly && path === workflowPath),
  );
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
  let triggerOnly = false;
  if (paths.includes(workflowPath)) {
    try {
      const mergeBase = execFileSync("git", ["merge-base", base, "HEAD"], {
        encoding: "utf8",
      }).trim();
      const contents = (revision) => execFileSync(
        "git", ["show", `${revision}:${workflowPath}`], { encoding: "utf8" },
      );
      triggerOnly = !workflowRequiresVerification(contents(mergeBase), contents("HEAD"));
    } catch {
      // A missing workflow at either revision must not skip verification.
    }
  }
  const verify = bundlesToVerify(paths, { triggerOnly });
  appendFileSync(
    process.env.GITHUB_OUTPUT,
    `required=${verify.length > 0}\ntargets=${verify.map((bundle) => `verify-${bundle}`).join(",")}\n`,
  );
}
