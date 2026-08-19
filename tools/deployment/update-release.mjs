#!/usr/bin/env node

import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import process from "node:process";

const PRODUCT_REPOSITORY =
  "873716897517.dkr.ecr.us-east-1.amazonaws.com/gradiated/prod/product";
const GATEWAY_REPOSITORY =
  "873716897517.dkr.ecr.us-east-1.amazonaws.com/gradiated/prod/gateway";
const IMAGES_START = "# deployment-images:start";
const IMAGES_END = "# deployment-images:end";

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

export async function updateRelease(options) {
  const sourceSha = requireMatch(
    "source SHA",
    options.sourceSha,
    /^[0-9a-f]{40}$/,
  );
  const productDigest = requireMatch(
    "product digest",
    options.productDigest,
    /^sha256:[0-9a-f]{64}$/,
  );
  const gatewayDigest = requireMatch(
    "gateway digest",
    options.gatewayDigest,
    /^sha256:[0-9a-f]{64}$/,
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
  const imageBlock = `${IMAGES_START}\nimages:\n  - name: ${PRODUCT_REPOSITORY}\n    newName: ${PRODUCT_REPOSITORY}\n    digest: ${productDigest}\n  - name: ${GATEWAY_REPOSITORY}\n    newName: ${GATEWAY_REPOSITORY}\n    digest: ${gatewayDigest}\n${IMAGES_END}`;
  kustomization = `${kustomization.slice(0, start)}${imageBlock}${kustomization.slice(end + IMAGES_END.length)}`;

  let metadata = await readFile(metadataPath, "utf8");
  metadata = replaceMetadataValue(metadata, "sourceRevision", sourceSha);
  metadata = replaceMetadataValue(metadata, "consoleRevision", sourceSha);
  metadata = replaceMetadataValue(
    metadata,
    "productImage",
    `${PRODUCT_REPOSITORY}@${productDigest}`,
  );
  metadata = replaceMetadataValue(
    metadata,
    "gatewayImage",
    `${GATEWAY_REPOSITORY}@${gatewayDigest}`,
  );

  await writeFile(kustomizationPath, kustomization);
  await writeFile(metadataPath, metadata);
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const argumentsByName = parseArguments(process.argv.slice(2));
  await updateRelease({
    root: argumentsByName.root,
    sourceSha: argumentsByName["source-sha"],
    productDigest: argumentsByName["product-digest"],
    gatewayDigest: argumentsByName["gateway-digest"],
  });
}
