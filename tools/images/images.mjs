import { createHash } from "node:crypto";
import { execFileSync, spawnSync } from "node:child_process";
import {
  appendFileSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  writeFileSync,
} from "node:fs";
import { pathToFileURL } from "node:url";
import { catalog } from "./catalog.mjs";

export const matches = (path, patterns) =>
  patterns.some((p) => (p.endsWith("/") ? path.startsWith(p) : path === p));
export const fingerprint = (name, entries) => {
  const image = catalog[name];
  if (!image || image.disabled)
    throw new Error(image?.disabled ?? `Unknown image: ${name}`);
  const relevant = entries.filter(
    ({ path }) =>
      matches(path, image.paths) && !matches(path, image.exclude ?? []),
  );
  if (!relevant.length) throw new Error(`No build inputs for ${name}`);
  return createHash("sha256")
    .update(
      JSON.stringify({ image, platform: "linux/amd64", entries: relevant }),
    )
    .digest("hex");
};
export const plan = (names, revision) => {
  if (!/^[0-9a-f]{40}$/.test(revision))
    throw new Error("Expected a full source SHA");
  if (
    !Array.isArray(names) ||
    !names.length ||
    new Set(names).size !== names.length
  )
    throw new Error("Expected unique image names");
  const entries = execFileSync("git", ["ls-tree", "-r", "-z", revision], {
    encoding: "utf8",
  })
    .split("\0")
    .filter(Boolean)
    .map((line) => {
      const [meta, path] = line.split("\t");
      return { path, meta };
    });
  return {
    include: names.map((name) => {
      const hash = fingerprint(name, entries);
      return { name, ...catalog[name], tag: `${name}-inputs-${hash}` };
    }),
  };
};
const emit = (name, value) =>
  appendFileSync(process.env.GITHUB_OUTPUT, `${name}=${value}\n`);
const awsDigest = (repository, tag) => {
  const result = spawnSync(
    "aws",
    [
      "ecr",
      "describe-images",
      "--repository-name",
      repository,
      "--image-ids",
      `imageTag=${tag}`,
      "--query",
      "imageDetails[0].imageDigest",
      "--output",
      "text",
    ],
    { encoding: "utf8" },
  );
  if (result.error) throw result.error;
  if (result.status !== 0) {
    if (result.stderr.includes("ImageNotFoundException")) return null;
    throw new Error(`ECR lookup failed: ${result.stderr}`);
  }
  const digest = result.stdout.trim();
  if (!/^sha256:[0-9a-f]{64}$/.test(digest))
    throw new Error("Invalid ECR digest");
  return digest;
};
const main = () => {
  const [command, ...args] = process.argv.slice(2);
  if (command === "plan")
    emit("matrix", JSON.stringify(plan(JSON.parse(args[0]), args[1])));
  else if (command === "lookup")
    emit("exists", String(awsDigest(args[0], args[1]) !== null));
  else if (command === "record") {
    const [name, repository, tag, source] = args;
    const digest = awsDigest(repository, tag);
    if (!digest) throw new Error("Published image is missing");
    mkdirSync("image-results", { recursive: true });
    writeFileSync(
      `image-results/${name}.json`,
      JSON.stringify({ name, repository, tag, digest, source }, null, 2),
    );
  } else if (command === "collect") {
    const names = JSON.parse(args[0]);
    const results = Object.fromEntries(
      readdirSync("image-results")
        .filter((file) => file.endsWith(".json"))
        .map((file) => {
          const record = JSON.parse(
            readFileSync(`image-results/${file}`, "utf8"),
          );
          if (
            !names.includes(record.name) ||
            record.source !== args[1] ||
            !/^sha256:[0-9a-f]{64}$/.test(record.digest)
          )
            throw new Error("Unexpected image result");
          return [record.name, record];
        }),
    );
    for (const name of names)
      if (!results[name]) throw new Error(`Missing image: ${name}`);
    emit("images", JSON.stringify(results));
    emit("product_digest", results.product?.digest ?? "");
    emit("gateway_digest", results.gateway?.digest ?? "");
  } else throw new Error("Unknown image command");
};
if (import.meta.url === pathToFileURL(process.argv[1]).href) main();
