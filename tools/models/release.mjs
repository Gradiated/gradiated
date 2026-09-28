import { createHash } from "node:crypto";
import { execFileSync, spawnSync } from "node:child_process";
import {
  appendFileSync,
  createReadStream,
  mkdirSync,
  readFileSync,
  writeFileSync,
} from "node:fs";
import { pathToFileURL } from "node:url";

const shared = [
  "product/inference/bundles/package.sh",
  "product/inference/images/nomad-base/base-id",
  "tools/models/release.mjs",
];
export const bundles = {
  "deepseek-v4-1-flash": [
    "product/inference/bundles/deepseek-v4-1-flash",
    "product/inference/images/deepseek-v4-1-flash/start.sh",
  ],
  "kev-9b": [
    "product/inference/bundles/kev-9b",
    "product/inference/runtimes/kev/adapter.py",
  ],
};
export const inputDigest = (baseImage, tree) => {
  if (!/@sha256:[0-9a-f]{64}$/.test(baseImage))
    throw new Error("A pinned base image is required");
  return createHash("sha256")
    .update(JSON.stringify({ baseImage, tree }))
    .digest("hex");
};
export const manifest = ({ source, baseImage, baseId, digest, bucket }) => {
  if (!/^[0-9a-f]{40}$/.test(source))
    throw new Error("Invalid source revision");
  if (!/^[0-9a-f]{64}$/.test(digest)) throw new Error("Invalid bundle digest");
  if (!/^[a-z0-9][a-z0-9.-]+$/.test(bucket))
    throw new Error("Invalid artifact bucket");
  inputDigest(baseImage, "");
  if (!/^[a-zA-Z0-9._-]+$/.test(baseId)) throw new Error("Invalid base ID");
  return {
    source,
    baseImage,
    baseId,
    sha256: digest,
    url: `s3::https://${bucket}.s3.us-east-1.amazonaws.com/bundles/sha256/${digest}.tar.gz`,
  };
};
const aws = (...args) => execFileSync("aws", args, { encoding: "utf8" });
const output = (key, value) =>
  appendFileSync(process.env.GITHUB_OUTPUT, `${key}=${value}\n`);
const fileDigest = async (file) => {
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(file)) hash.update(chunk);
  return hash.digest("hex");
};

const main = async () => {
  const [command, bundle, source, baseImage, bucket] = process.argv.slice(2);
  if (command === "list") {
    console.log(JSON.stringify(Object.keys(bundles)));
    return;
  }
  if (!Object.hasOwn(bundles, bundle)) throw new Error(`Unknown bundle ${bundle}`);
  if (!/^[0-9a-f]{40}$/.test(source))
    throw new Error("Invalid source revision");
  const tree = execFileSync(
    "git",
    ["ls-tree", "-r", source, "--", ...shared, ...bundles[bundle]],
    { encoding: "utf8" },
  );
  const identity = inputDigest(baseImage, tree);
  const key = `releases/${bundle}/${identity}.json`;
  mkdirSync("model-release", { recursive: true });
  if (command === "lookup") {
    const result = spawnSync(
      "aws",
      ["s3api", "head-object", "--bucket", bucket, "--key", key],
      { encoding: "utf8" },
    );
    if (result.error) throw result.error;
    if (result.status !== 0 && !/\(404\)|Not Found/.test(result.stderr)) {
      throw new Error(`Artifact lookup failed: ${result.stderr}`);
    }
    output("exists", String(result.status === 0));
    if (result.status === 0) {
      aws(
        "s3",
        "cp",
        `s3://${bucket}/${key}`,
        "model-release/release.json",
        "--only-show-errors",
      );
    }
  } else if (command === "publish") {
    const digest = await fileDigest("model-release/runtime.tar.gz");
    const release = manifest({
      source,
      baseImage,
      bucket,
      digest,
      baseId: readFileSync(
        "product/inference/images/nomad-base/base-id",
        "utf8",
      ).trim(),
    });
    writeFileSync(
      "model-release/release.json",
      JSON.stringify(release, null, 2) + "\n",
    );
    // Publish the archive first. A release record never points to a pending upload.
    aws(
      "s3",
      "cp",
      "model-release/runtime.tar.gz",
      `s3://${bucket}/bundles/sha256/${digest}.tar.gz`,
      "--only-show-errors",
    );
    aws(
      "s3",
      "cp",
      "model-release/release.json",
      `s3://${bucket}/${key}`,
      "--only-show-errors",
    );
  } else {
    throw new Error("Expected list, lookup or publish");
  }
};
if (import.meta.url === pathToFileURL(process.argv[1]).href) await main();
