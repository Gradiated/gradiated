import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { updateRelease } from "./update-release.mjs";

const SOURCE_SHA = "a".repeat(40);
const PRODUCT_DIGEST = `sha256:${"b".repeat(64)}`;
const GATEWAY_DIGEST = `sha256:${"c".repeat(64)}`;

async function fixture() {
  const root = await mkdtemp(path.join(os.tmpdir(), "gradiated-release-"));
  const workloads = path.join(
    root,
    "infra/environments/prod/us-east-1/kubernetes/workloads",
  );
  await mkdir(workloads, { recursive: true });
  await writeFile(
    path.join(workloads, "kustomization.yaml"),
    "apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\n# deployment-images:start\n# deployment-images:end\n",
  );
  await writeFile(
    path.join(workloads, "release-metadata.yaml"),
    'data:\n  sourceRevision: "unreleased"\n  consoleRevision: "unreleased"\n  productImage: "unreleased"\n  gatewayImage: "unreleased"\n',
  );
  return { root, workloads };
}

test("updates one complete production release", async () => {
  const { root, workloads } = await fixture();
  await updateRelease({
    root,
    sourceSha: SOURCE_SHA,
    productDigest: PRODUCT_DIGEST,
    gatewayDigest: GATEWAY_DIGEST,
  });

  const kustomization = await readFile(
    path.join(workloads, "kustomization.yaml"),
    "utf8",
  );
  const metadata = await readFile(
    path.join(workloads, "release-metadata.yaml"),
    "utf8",
  );
  assert.match(kustomization, new RegExp(`digest: ${PRODUCT_DIGEST}`));
  assert.match(kustomization, new RegExp(`digest: ${GATEWAY_DIGEST}`));
  assert.match(metadata, new RegExp(`sourceRevision: "${SOURCE_SHA}"`));
  assert.match(metadata, new RegExp(`consoleRevision: "${SOURCE_SHA}"`));
  assert.match(metadata, new RegExp(`productImage: ".*@${PRODUCT_DIGEST}"`));
  assert.match(metadata, new RegExp(`gatewayImage: ".*@${GATEWAY_DIGEST}"`));
});

test("rejects a non-immutable image reference", async () => {
  const { root } = await fixture();
  await assert.rejects(
    updateRelease({
      root,
      sourceSha: SOURCE_SHA,
      productDigest: "latest",
      gatewayDigest: GATEWAY_DIGEST,
    }),
    /Invalid product digest/,
  );
});
