import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { createReadStream } from "node:fs";
import { appendFile, mkdir, readFile, writeFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";
import { catalog } from "./catalog.mjs";
import { plan, awsDigest } from "./images.mjs";

const verificationPaths = [
  ".trivyignore",
  "mise.toml",
  "tools/security/scan_report.py",
  "tools/images/",
  ".github/workflows/tests.yml",
];
const tree = (revision, paths) =>
  execFileSync("git", ["ls-tree", "-r", "-z", revision, "--", ...paths]);
export const verificationKey = (image, revision) =>
  createHash("sha256")
    .update(image.tag)
    .update(tree(revision, verificationPaths))
    .digest("hex");
export const selectImages = (
  base,
  revision,
  names = [
    "product",
    "gateway",
    "proxy",
    "collector",
    "gpu-controller",
    "gpu-base",
    "falco",
    "temporal-ui",
  ],
) => {
  const images = plan(names, revision).include;
  let before;
  try {
    before = plan(names, base).include;
  } catch {
    return images;
  }
  return images.filter(
    (image, i) =>
      verificationKey(image, revision) !== verificationKey(before[i], base),
  );
};
const hashArchive = async (path) => {
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(path)) hash.update(chunk);
  return hash.digest("hex");
};
const output = async (key, value) => {
  if (process.env.GITHUB_OUTPUT)
    await appendFile(process.env.GITHUB_OUTPUT, `${key}=${value}\n`);
};
const api = async (path) => {
  const response = await fetch(
    `https://api.github.com/repos/${process.env.GITHUB_REPOSITORY}/${path}`,
    {
      headers: {
        Authorization: `Bearer ${process.env.GITHUB_TOKEN}`,
        Accept: "application/vnd.github+json",
      },
      signal: AbortSignal.timeout(30_000),
    },
  );
  if (!response.ok)
    throw new Error(`GitHub artifact lookup failed: ${response.status}`);
  return response.json();
};
export const trustedRun = (run, repository) =>
  run.status === "completed" &&
  run.conclusion === "success" &&
  run.path === ".github/workflows/tests.yml" &&
  run.head_repository?.full_name === repository &&
  (run.event === "pull_request" ||
    (run.event === "workflow_dispatch" && run.head_branch === "main"));
export const findArtifact = async (name, fresh = false) => {
  for (let page = 1; page <= 3; page++) {
    const { artifacts } = await api(
      `actions/artifacts?name=${encodeURIComponent(name)}&per_page=100&page=${page}`,
    );
    for (const artifact of artifacts) {
      if (
        artifact.expired ||
        artifact.name !== name ||
        !artifact.workflow_run?.id
      )
        continue;
      if (
        fresh &&
        Date.now() - Date.parse(artifact.created_at) > 24 * 60 * 60 * 1000
      )
        continue;
      const run = await api(`actions/runs/${artifact.workflow_run.id}`);
      if (trustedRun(run, process.env.GITHUB_REPOSITORY)) return artifact;
    }
    if (artifacts.length < 100) return null;
  }
  return null;
};
export const validateMetadata = (metadata, image, key, hash) => {
  if (
    metadata.schema !== 1 ||
    metadata.name !== image.name ||
    metadata.tag !== image.tag ||
    metadata.verificationKey !== key ||
    metadata.archiveSha256 !== hash
  )
    throw new Error(
      "CI image metadata does not match the release inputs or archive",
    );
};
const main = async () => {
  const [command, name, revision, directory = "ci-image"] =
    process.argv.slice(2);
  if (command === "select") {
    await output(
      "matrix",
      JSON.stringify({ include: selectImages(name, revision) }),
    );
    await output("required", String(selectImages(name, revision).length > 0));
    return;
  }
  const image = plan([name], revision).include[0];
  const key = verificationKey(image, revision);
  const artifactName = `ci-image-${name}-${key}`;
  await output("artifact", artifactName);
  if (
    command === "fetch" &&
    ["product", "gateway", "proxy", "collector", "gpu-controller"].includes(
      name,
    )
  ) {
    const metadata = execFileSync(
      "git",
      [
        "show",
        "origin/main:infra/environments/prod/us-east-1/kubernetes/workloads/release-metadata.yaml",
      ],
      { encoding: "utf8" },
    );
    const previous = metadata.match(
      /^  sourceRevision: "([a-f0-9]{40})"$/m,
    )?.[1];
    if (previous && plan([name], previous).include[0].tag === image.tag) {
      const contents =
        name === "gpu-controller"
          ? execFileSync(
              "git",
              [
                "show",
                "origin/main:infra/environments/prod/us-east-1/kubernetes/gpu-inference/controller.yaml",
              ],
              { encoding: "utf8" },
            )
          : metadata;
      const digest =
        name === "gpu-controller"
          ? contents.match(/image: [^\s]+@(sha256:[a-f0-9]{64})/)?.[1]
          : contents.match(
              new RegExp(
                `^  ${name}Image: "[^\"]+@(sha256:[a-f0-9]{64})"$`,
                "m",
              ),
            )?.[1];
      if (digest) {
        await output("digest", digest);
        await output("publish", "false");
        return;
      }
    }
  }
  if (command === "record") {
    await mkdir(directory, { recursive: true });
    await writeFile(
      `${directory}/image.json`,
      JSON.stringify({
        schema: 1,
        name,
        tag: image.tag,
        verificationKey: key,
        archiveSha256: await hashArchive(`${directory}/image.tar`),
      }),
    );
    return;
  }
  if (command !== "find" && command !== "fetch")
    throw new Error("Unknown verification command");
  const artifact = await findArtifact(artifactName, command === "find");
  await output("reused", String(Boolean(artifact)));
  if (command === "find") return;
  if (!artifact) {
    // Only unchanged inputs may reuse an image from before artifact promotion existed.
    const changed = selectImages(`${revision}^`, revision, [name]);
    if (changed.length)
      throw new Error(
        `No passing CI image artifact for ${name}. Rebase/retest the PR; deployment never rebuilds or scans images.`,
      );
    let tag = image.tag;
    if (!awsDigest(image.repository, tag)) {
      const published = JSON.parse(
        execFileSync(
          "aws",
          [
            "ecr",
            "describe-images",
            "--repository-name",
            image.repository,
            "--filter",
            "tagStatus=TAGGED",
            "--output",
            "json",
          ],
          { encoding: "utf8" },
        ),
      ).imageDetails;
      tag = published
        .sort(
          (a, b) => Date.parse(b.imagePushedAt) - Date.parse(a.imagePushedAt),
        )
        .flatMap((record) => record.imageTags ?? [])
        .find((value) => value.startsWith(`${image.tag}-`));
      if (!tag)
        throw new Error(`No published or CI-verified image for ${name}`);
    }
    await output("tag", tag);
    await output("publish", "false");
    return;
  }
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
      artifactName,
      "--dir",
      directory,
    ],
    { stdio: "inherit" },
  );
  const metadata = JSON.parse(
    await readFile(`${directory}/image.json`, "utf8"),
  );
  validateMetadata(
    metadata,
    image,
    key,
    await hashArchive(`${directory}/image.tar`),
  );
  const tag = `${image.tag}-${metadata.archiveSha256.slice(0, 12)}`;
  await output("tag", tag);
  await output("publish", String(!awsDigest(image.repository, tag)));
};
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href)
  await main();
