#!/usr/bin/env node

import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const REGISTRY = "873716897517.dkr.ecr.us-east-1.amazonaws.com/gradiated/prod";
const IMAGES_START = "# deployment-images:start";
const IMAGES_END = "# deployment-images:end";
// Each released image: the metadata key that records it and the manifests that run it.
const IMAGES = [
  {
    name: "product",
    metadataKey: "productImage",
    manifests: [
      "api.yaml",
      "clickhouse-migrate.yaml",
      "worker.yaml",
      "../operations/ops-mcp/workload.yaml",
    ],
  },
  { name: "gateway", metadataKey: "gatewayImage", manifests: ["gateway.yaml"] },
  { name: "proxy", metadataKey: "proxyImage", manifests: ["proxy.yaml"] },
  { name: "collector", metadataKey: "collectorImage", manifests: ["collector.yaml"] },
];

const repository = (name) => `${REGISTRY}/${name}`;

function parseArguments(values) {
  const result = { root: process.cwd() };
  for (let index = 0; index < values.length; index += 2) {
    const name = values[index];
    const value = values[index + 1];
    if (!name?.startsWith("--") || value === undefined) {
      throw new Error(`Invalid argument sequence at ${name ?? "end of input"}`);
    }
    result[name.slice(2)] = value;
  }
  return result;
}

function requireMatch(name, value, expression) {
  if (!expression.test(value ?? "")) {
    throw new Error(`Invalid ${name}`);
  }
  return value;
}

function replaceMetadataValue(contents, key, value) {
  const expression = new RegExp(`^(  ${key}: )"[^"]*"$`, "m");
  if (!expression.test(contents)) {
    throw new Error(`Missing release metadata key: ${key}`);
  }
  return contents.replace(expression, `$1"${value}"`);
}

function replaceImageReference(contents, repository, digest, file) {
  const escapedRepository = repository.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const expression = new RegExp(
    `${escapedRepository}(?:@sha256:[0-9a-f]{64}|:[^\\s\"']+)`,
    "g",
  );
  if (!contents.match(expression)) {
    throw new Error(`Missing ${repository} image reference in ${file}`);
  }
  return contents.replace(expression, `${repository}@${digest}`);
}

export async function updateRelease(options) {
  const sourceSha = requireMatch(
    "source SHA",
    options.sourceSha,
    /^[0-9a-f]{40}$/,
  );
  const digests = Object.fromEntries(
    IMAGES.map(({ name }) => [
      name,
      requireMatch(`${name} digest`, options.digests?.[name], /^sha256:[0-9a-f]{64}$/),
    ]),
  );
  const root = path.resolve(options.root);
  const workloads = path.join(
    root,
    "infra/environments/prod/us-east-1/kubernetes/workloads",
  );
  const kustomizationPath = path.join(workloads, "kustomization.yaml");
  const metadataPath = path.join(workloads, "release-metadata.yaml");

  let kustomization = await readFile(kustomizationPath, "utf8");
  const start = kustomization.indexOf(IMAGES_START);
  const end = kustomization.indexOf(IMAGES_END);
  if (start < 0 || end < start) {
    throw new Error("Missing deployment image markers");
  }
  const entries = IMAGES.map(
    ({ name }) =>
      `  - name: ${repository(name)}\n    newName: ${repository(name)}\n    digest: ${digests[name]}\n`,
  ).join("");
  const imageBlock = `${IMAGES_START}\nimages:\n${entries}${IMAGES_END}`;
  kustomization = `${kustomization.slice(0, start)}${imageBlock}${kustomization.slice(end + IMAGES_END.length)}`;

  let metadata = await readFile(metadataPath, "utf8");
  metadata = replaceMetadataValue(metadata, "sourceRevision", sourceSha);
  metadata = replaceMetadataValue(metadata, "consoleRevision", sourceSha);
  for (const { name, metadataKey } of IMAGES) {
    metadata = replaceMetadataValue(
      metadata,
      metadataKey,
      `${repository(name)}@${digests[name]}`,
    );
  }

  for (const { name, manifests } of IMAGES) {
    for (const file of manifests) {
      const manifestPath = path.join(workloads, file);
      const manifest = await readFile(manifestPath, "utf8");
      await writeFile(
        manifestPath,
        replaceImageReference(manifest, repository(name), digests[name], file),
      );
    }
  }

  await writeFile(kustomizationPath, kustomization);
  await writeFile(metadataPath, metadata);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const argumentsByName = parseArguments(process.argv.slice(2));
  await updateRelease({
    root: argumentsByName.root,
    sourceSha: argumentsByName["source-sha"],
    digests: Object.fromEntries(
      IMAGES.map(({ name }) => [name, argumentsByName[`${name}-digest`]]),
    ),
  });
}
