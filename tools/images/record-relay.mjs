import { readFileSync, writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
export const updateRelay = (source, images, account) => {
  const image = images["nomad-relay"];
  if (
    !/^\d{12}$/.test(account) ||
    !/^sha256:[0-9a-f]{64}$/.test(image?.digest) ||
    image.repository !== "gradiated/prod/inference"
  )
    throw new Error("Invalid relay release");
  const pattern =
    /^(\s+image: )(?:nomad-relay:deployment-pending|\d{12}\.dkr\.ecr\.us-east-1\.amazonaws\.com\/gradiated\/prod\/inference@sha256:[0-9a-f]{64})$/gm;
  if ([...source.matchAll(pattern)].length !== 1)
    throw new Error("Expected one relay image reference");
  return source.replace(
    pattern,
    `$1${account}.dkr.ecr.us-east-1.amazonaws.com/${image.repository}@${image.digest}`,
  );
};
if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  const path =
    "infra/environments/prod/us-east-1/kubernetes/nomad/nomad-relay.yaml";
  writeFileSync(
    path,
    updateRelay(
      readFileSync(path, "utf8"),
      JSON.parse(process.env.IMAGES),
      process.env.AWS_ACCOUNT_ID,
    ),
  );
}
