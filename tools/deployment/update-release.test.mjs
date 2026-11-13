import assert from "node:assert/strict";
import { mkdtemp, mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { updateRelease } from "./update-release.mjs";

const SOURCE_SHA = "a".repeat(40);
const PRODUCT_DIGEST = `sha256:${"b".repeat(64)}`;
const GATEWAY_DIGEST = `sha256:${"c".repeat(64)}`;
const PROXY_DIGEST = `sha256:${"e".repeat(64)}`;
const COLLECTOR_DIGEST = `sha256:${"f".repeat(64)}`;
const DIGESTS = {
  product: PRODUCT_DIGEST,
  gateway: GATEWAY_DIGEST,
  proxy: PROXY_DIGEST,
  collector: COLLECTOR_DIGEST,
};

async function fixture() {
  const root = await mkdtemp(path.join(os.tmpdir(), "gradiated-release-"));
  const workloads = path.join(
    root,
    "infra/environments/prod/us-east-1/kubernetes/workloads",
  );
  await mkdir(workloads, { recursive: true });
  await mkdir(path.join(workloads, "recovery"), { recursive: true });
  await writeFile(
    path.join(workloads, "recovery/cronjobs.yaml"),
    "image: 873716897517.dkr.ecr.us-east-1.amazonaws.com/gradiated/prod/product:old\n".repeat(
      3,
    ),
  );
  const ops = path.join(workloads, "../operations/ops-mcp");
  await mkdir(ops, { recursive: true });
  await writeFile(
    path.join(ops, "workload.yaml"),
    "image: 873716897517.dkr.ecr.us-east-1.amazonaws.com/gradiated/prod/product:ops-mcp-release-required\n",
  );
  const gpu = path.join(workloads, "../gpu-inference");
  await mkdir(gpu, { recursive: true });
  await writeFile(
    path.join(gpu, "gpu-fleet.yaml"),
    "image: 873716897517.dkr.ecr.us-east-1.amazonaws.com/gradiated/prod/product:gpu-fleet-release-required\n",
  );
  await writeFile(
    path.join(workloads, "kustomization.yaml"),
    "apiVersion: kustomize.config.k8s.io/v1beta1\nkind: Kustomization\n# deployment-images:start\n# deployment-images:end\n",
  );
  await writeFile(
    path.join(workloads, "release-metadata.yaml"),
    'data:\n  sourceRevision: "unreleased"\n  consoleRevision: "unreleased"\n  productImage: "unreleased"\n  gatewayImage: "unreleased"\n  proxyImage: "unreleased"\n  collectorImage: "unreleased"\n',
  );
  await writeFile(
    path.join(workloads, "api.yaml"),
    `image: 873716897517.dkr.ecr.us-east-1.amazonaws.com/gradiated/prod/product:old\n`,
  );
  await writeFile(
    path.join(workloads, "clickhouse-migrate.yaml"),
    `image: 873716897517.dkr.ecr.us-east-1.amazonaws.com/gradiated/prod/product@sha256:${"d".repeat(64)}\n`,
  );
  await writeFile(
    path.join(workloads, "mcp.yaml"),
    `image: 873716897517.dkr.ecr.us-east-1.amazonaws.com/gradiated/prod/product:old\n`,
  );
  await writeFile(
    path.join(workloads, "worker.yaml"),
    `image: 873716897517.dkr.ecr.us-east-1.amazonaws.com/gradiated/prod/product:old\n`,
  );
  await writeFile(
    path.join(workloads, "temporal-worker.yaml"),
    `image: 873716897517.dkr.ecr.us-east-1.amazonaws.com/gradiated/prod/product:old\n`,
  );
  await writeFile(
    path.join(workloads, "gateway.yaml"),
    `image: 873716897517.dkr.ecr.us-east-1.amazonaws.com/gradiated/prod/gateway:old\n`,
  );
  await writeFile(
    path.join(workloads, "proxy.yaml"),
    `image: 873716897517.dkr.ecr.us-east-1.amazonaws.com/gradiated/prod/proxy@sha256:${"0".repeat(64)}\n`,
  );
  await writeFile(
    path.join(workloads, "collector.yaml"),
    `image: 873716897517.dkr.ecr.us-east-1.amazonaws.com/gradiated/prod/collector@sha256:${"0".repeat(64)}\n`,
  );
  await writeFile(
    path.join(workloads, "rollout-analysis.yaml"),
    "image: 873716897517.dkr.ecr.us-east-1.amazonaws.com/gradiated/prod/product:old\n",
  );
  return { root, workloads };
}

test("updates one complete production release", async () => {
  const { root, workloads } = await fixture();
  await updateRelease({ root, sourceSha: SOURCE_SHA, digests: DIGESTS });

  const kustomization = await readFile(
    path.join(workloads, "kustomization.yaml"),
    "utf8",
  );
  const metadata = await readFile(
    path.join(workloads, "release-metadata.yaml"),
    "utf8",
  );
  const api = await readFile(path.join(workloads, "api.yaml"), "utf8");
  const clickhouseMigrate = await readFile(
    path.join(workloads, "clickhouse-migrate.yaml"),
    "utf8",
  );
  const worker = await readFile(path.join(workloads, "worker.yaml"), "utf8");
  const gateway = await readFile(path.join(workloads, "gateway.yaml"), "utf8");
  const proxy = await readFile(path.join(workloads, "proxy.yaml"), "utf8");
  const collector = await readFile(
    path.join(workloads, "collector.yaml"),
    "utf8",
  );
  assert.match(kustomization, new RegExp(`digest: ${PRODUCT_DIGEST}`));
  assert.match(kustomization, new RegExp(`digest: ${GATEWAY_DIGEST}`));
  assert.match(
    kustomization,
    new RegExp(`prod/proxy\\n    digest: ${PROXY_DIGEST}`),
  );
  assert.match(api, new RegExp(`product@${PRODUCT_DIGEST}`));
  assert.match(
    await readFile(path.join(workloads, "rollout-analysis.yaml"), "utf8"),
    new RegExp(`product@${PRODUCT_DIGEST}`),
  );
  assert.match(clickhouseMigrate, new RegExp(`product@${PRODUCT_DIGEST}`));
  assert.match(worker, new RegExp(`product@${PRODUCT_DIGEST}`));
  assert.match(
    await readFile(path.join(workloads, "mcp.yaml"), "utf8"),
    new RegExp(`product@${PRODUCT_DIGEST}`),
  );
  const temporalWorker = await readFile(
    path.join(workloads, "temporal-worker.yaml"),
    "utf8",
  );
  assert.match(temporalWorker, new RegExp(`product@${PRODUCT_DIGEST}`));
  const ops = await readFile(
    path.join(workloads, "../operations/ops-mcp/workload.yaml"),
    "utf8",
  );
  assert.match(ops, new RegExp(`product@${PRODUCT_DIGEST}`));
  const fleet = await readFile(
    path.join(workloads, "../gpu-inference/gpu-fleet.yaml"),
    "utf8",
  );
  assert.match(fleet, new RegExp(`product@${PRODUCT_DIGEST}`));
  assert.match(gateway, new RegExp(`gateway@${GATEWAY_DIGEST}`));
  assert.match(proxy, new RegExp(`proxy@${PROXY_DIGEST}`));
  assert.match(collector, new RegExp(`collector@${COLLECTOR_DIGEST}`));
  assert.match(
    kustomization,
    new RegExp(`prod/collector\\n    digest: ${COLLECTOR_DIGEST}`),
  );
  assert.match(metadata, new RegExp(`sourceRevision: "${SOURCE_SHA}"`));
  assert.match(metadata, new RegExp(`consoleRevision: "${SOURCE_SHA}"`));
  assert.match(metadata, new RegExp(`productImage: ".*@${PRODUCT_DIGEST}"`));
  assert.match(metadata, new RegExp(`gatewayImage: ".*@${GATEWAY_DIGEST}"`));
  assert.match(metadata, new RegExp(`proxyImage: ".*@${PROXY_DIGEST}"`));
  assert.match(
    metadata,
    new RegExp(`collectorImage: ".*@${COLLECTOR_DIGEST}"`),
  );
});

test("rejects a non-immutable image reference", async () => {
  const { root } = await fixture();
  await assert.rejects(
    updateRelease({
      root,
      sourceSha: SOURCE_SHA,
      digests: { ...DIGESTS, product: "latest" },
    }),
    /Invalid product digest/,
  );
});

test("refuses a release without every image", async () => {
  const { root } = await fixture();
  const { proxy: _, ...withoutProxy } = DIGESTS;

  await assert.rejects(
    updateRelease({ root, sourceSha: SOURCE_SHA, digests: withoutProxy }),
    /Invalid proxy digest/,
  );
});

test("pins the GPU controller through the same immutable release", async () => {
  const { root } = await fixture();
  const file = path.join(
    root,
    "infra/environments/prod/us-east-1/kubernetes/gpu-inference/controller.yaml",
  );
  await mkdir(path.dirname(file), { recursive: true });
  await writeFile(
    file,
    "image: 873716897517.dkr.ecr.us-east-1.amazonaws.com/gradiated/prod/product:gpu-controller-old\n",
  );
  const digest = `sha256:${"9".repeat(64)}`;
  await updateRelease({
    root,
    sourceSha: SOURCE_SHA,
    digests: DIGESTS,
    gpuControllerDigest: digest,
  });
  assert.equal(
    await readFile(file, "utf8"),
    `image: 873716897517.dkr.ecr.us-east-1.amazonaws.com/gradiated/prod/product@${digest}\n`,
  );
});

test("release updates all weekly recovery worker images", async () => {
  const { root } = await fixture();
  await updateRelease({ root, sourceSha: SOURCE_SHA, digests: DIGESTS });
  const manifest = await readFile(
    path.join(
      root,
      "infra/environments/prod/us-east-1/kubernetes/workloads/recovery/cronjobs.yaml",
    ),
    "utf8",
  );
  assert.equal(manifest.split(PRODUCT_DIGEST).length - 1, 3);
  assert.ok(!manifest.includes(":old"));
});

test("records and replaces the workflow identity independently of selected source", async () => {
  const { root, workloads } = await fixture();
  await updateRelease({
    root,
    sourceSha: SOURCE_SHA,
    digests: DIGESTS,
    deploymentRunId: "123",
  });
  let metadata = await readFile(
    path.join(workloads, "release-metadata.yaml"),
    "utf8",
  );
  assert.match(metadata, /  deploymentRunId: "123"/);
  await updateRelease({
    root,
    sourceSha: SOURCE_SHA,
    digests: DIGESTS,
    deploymentRunId: "456",
  });
  metadata = await readFile(
    path.join(workloads, "release-metadata.yaml"),
    "utf8",
  );
  assert.match(metadata, /  deploymentRunId: "456"/);
  assert.equal((metadata.match(/deploymentRunId/g) || []).length, 1);
  assert.match(metadata, new RegExp(`sourceRevision: "${SOURCE_SHA}"`));
  await assert.rejects(
    updateRelease({
      root,
      sourceSha: SOURCE_SHA,
      digests: DIGESTS,
      deploymentRunId: "invalid",
    }),
    /Invalid deployment run ID/,
  );
});
