import { execFileSync } from "node:child_process";
import { readFileSync, readdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const jobs = resolve(root, "product/inference/nomad/jobs");
const target = resolve(root, "infra/environments/prod/us-east-1/kubernetes/workloads/observability/model-replica-rules.yaml");
const bundles = JSON.parse(execFileSync("node", [resolve(root, "tools/models/release.mjs"), "list"], { encoding: "utf8" }));
const rules = [];

for (const file of readdirSync(jobs).filter((name) => name.endsWith(".vars.hcl")).sort()) {
  const name = file.slice(0, -".vars.hcl".length);
  const release = bundles.includes(name) ? [
    "-var=bundle_url=https://example.invalid/bundle.tar.gz",
    `-var=bundle_sha256=${"0".repeat(64)}`,
    "-var=base_id=test-base-v1",
  ] : [];
  const { Job: job } = JSON.parse(execFileSync("docker", [
    "run", "--rm", "--network", "none", "--entrypoint", "nomad", "-v", `${jobs}:/jobs:ro`,
    "hashicorp/nomad@sha256:b964829b94c5493f3b543bb409b60c335a9ca03f21d9fac8b4cdd2af18b331c9",
    "job", "run", "-output", ...release, `-var-file=/jobs/${file}`, `/jobs/${name}.nomad.hcl`,
  ], { encoding: "utf8" }));
  const model = job.Meta?.gradiated_model_id;
  if (!model) continue;

  if (job.Type !== "service") throw new Error(`${name}: model job must be a service`);
  const count = job.TaskGroups.reduce((total, group) => total + group.Count, 0);
  if (!Number.isSafeInteger(count) || count < 0) throw new Error(`${name}: invalid replica count`);
  rules.push({ record: "gradiated_model_desired_replicas", expr: `vector(${count})`, labels: { model, nomad_job: job.ID } });
}

if (!rules.length) throw new Error("No model jobs found; refusing to erase desired replicas");
const manifest = {
  apiVersion: "monitoring.coreos.com/v1", kind: "PrometheusRule",
  metadata: { name: "gradiated-model-replicas", labels: { release: "observability" }, annotations: {
    "gradiated.com/generated-by": "node tools/nomad/model-replica-rules.mjs",
  } },
  spec: { groups: [{ name: "gradiated.models.desired", rules }] },
};
const content = `${JSON.stringify(manifest, null, 2)}\n`;
if (process.argv.includes("--check")) {
  if (readFileSync(target, "utf8") !== content) throw new Error("Model replica rules are stale; run node tools/nomad/model-replica-rules.mjs");
} else {
  writeFileSync(target, content);
}
