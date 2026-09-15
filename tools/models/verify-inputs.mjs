import { execFileSync } from "node:child_process";
import { appendFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { catalog } from "../images/catalog.mjs";
import { matches } from "../images/images.mjs";

// Compare the full PR against its base. Comparing only the last push could skip
// an earlier runtime change whose verification failed or was cancelled.
export const needsRuntimeVerification = (paths) =>
  paths.some(
    (path) =>
      !path.endsWith(".md") &&
      (matches(path, catalog["nomad-base"].paths) ||
        path.startsWith("product/inference/bundles/") ||
        path === "product/inference/images/deepseek-v4-1-flash/start.sh" ||
        path === "product/inference/.dockerignore" ||
        path === ".github/workflows/model-deployment.yml" ||
        path === "tools/models/verify-inputs.mjs"),
  );

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
  appendFileSync(
    process.env.GITHUB_OUTPUT,
    `required=${needsRuntimeVerification(paths)}\n`,
  );
}
