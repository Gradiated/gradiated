import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import { isDeepStrictEqual } from "node:util";
import { resolve, dirname } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
export const plan = JSON.parse(
  readFileSync(
    resolve(root, "product/inference/gpu/canaries/glm-dealign-sglang.json"),
    "utf8",
  ),
);
const bucket = "gradiated-prod-model-artifacts-873716897517";
// The launcher profile owns the limit the runtime enforces and Desmond reports.
export const activeRequests = () =>
  JSON.parse(
    execFileSync(
      "python3",
      [
        "-c",
        "import importlib.util, json, sys; sys.dont_write_bytecode = True; spec = importlib.util.spec_from_file_location('render', sys.argv[1]); render = importlib.util.module_from_spec(spec); spec.loader.exec_module(render); print(json.dumps(render.glm_sglang_profiles()['b300-pcp2']['active_requests']))",
        resolve(root, "tools/gpu/render-config.py"),
      ],
      { encoding: "utf8" },
    ),
  );

export const stageCanary = ({
  models,
  runtimes,
  pins,
  release,
  expectedSource,
  promote = false,
}) => {
  if (
    !/^[0-9a-f]{40}$/.test(expectedSource) ||
    release.source !== expectedSource
  )
    throw new Error(
      "The release must match the explicitly qualified source revision",
    );
  if (release.bundle !== plan.bundle || !/^[0-9a-f]{64}$/.test(release.sha256))
    throw new Error("Expected an immutable SGLang GLM bundle release");
  if (
    release.baseId !== pins.hostBundle.baseId ||
    !/@sha256:[0-9a-f]{64}$/.test(release.baseImage)
  )
    throw new Error("The release must support the pinned host base");
  const expectedUrl = `s3::https://${bucket}.s3.us-east-1.amazonaws.com/bundles/sha256/${release.sha256}.tar.gz`;
  if (release.url !== expectedUrl)
    throw new Error("The release archive path does not match its digest");
  const primary = models[plan.primary];
  if (!primary || runtimes[primary.runtime]?.model_id !== plan.model)
    throw new Error("The existing primary must serve the exact canary model");
  if (
    Object.entries(models).some(
      ([name, model]) =>
        name !== plan.name && model.canary_for === plan.primary,
    )
  )
    throw new Error(
      "A different canary already uses the primary's canary budget",
    );

  const runtime = {
    image: `gradiated/glm-sglang-bundle@sha256:${release.sha256}`,
    bundles: { [release.baseId]: release.sha256 },
    model_id: plan.runtime_model,
    release: {
      schema_version: 1,
      model_path: plan.checkpoint,
      model_revision: plan.checkpoint_revision,
      tokenizer_path: plan.checkpoint,
      tokenizer_revision: plan.checkpoint_revision,
      runtime_revision: `glm-dealign-sglang-${release.sha256.slice(0, 12)}`,
      runtime_model_name: plan.checkpoint,
    },
    gpus: plan.gpus,
    active_requests: activeRequests(),
    cpu: plan.cpu,
    memory: plan.memory,
    startup_timeout: 3600,
    warmup: true,
    environment: { TENSOR_PARALLEL_SIZE: "2" },
  };
  const candidate = {
    runtime: release.sha256,
    replicas: 1,
    min_available: 1,
    canary_for: plan.primary,
    serving_model_id: plan.model,
    serving_mode: promote ? "production" : "qualification",
    progress_deadline_seconds: 5400,
    max_surge: 0,
    max_unavailable: 1,
    node_selector: {
      "gradiated.com/provider": "runpod",
      "nvidia.com/gpu.product": "B300",
      "gradiated.com/instance-id": plan.instance_id,
    },
    autoscaling: { max_replicas: 1 },
  };
  const existing = models[plan.name];
  const isolated = { ...candidate, serving_mode: "qualification" };
  if (
    promote &&
    (!existing ||
      (!isDeepStrictEqual(existing, isolated) &&
        !isDeepStrictEqual(existing, candidate)))
  )
    throw new Error(
      "Promotion requires the exact previously isolated canary and bundle",
    );
  if (
    existing &&
    !(promote && isDeepStrictEqual(existing, isolated)) &&
    !isDeepStrictEqual(existing, candidate)
  )
    throw new Error(
      "An existing canary or manual rollback must be changed explicitly",
    );
  if (promote && !isDeepStrictEqual(runtimes[release.sha256], runtime))
    throw new Error(
      "Promotion requires the existing immutable isolated runtime",
    );
  if (
    runtimes[release.sha256] &&
    !isDeepStrictEqual(runtimes[release.sha256], runtime)
  )
    throw new Error(
      "The runtime digest already has a different immutable definition",
    );

  return {
    models: { ...models, [plan.name]: candidate },
    runtimes: { ...runtimes, [release.sha256]: runtime },
  };
};

if (
  process.argv[1] &&
  pathToFileURL(resolve(process.argv[1])).href === import.meta.url
) {
  const args = process.argv.slice(2);
  const write = args.includes("--write");
  const promote = args.includes("--promote");
  const positional = args.filter(
    (value) => !["--write", "--promote"].includes(value),
  );
  if (positional.length !== 2)
    throw new Error(
      "usage: stage-glm-sglang-canary.mjs RELEASE_JSON QUALIFIED_SOURCE_SHA [--write] [--promote]",
    );
  const modelsPath = resolve(
    root,
    "infra/environments/prod/us-east-1/kubernetes/gpu-inference/models.json",
  );
  const runtimesPath = resolve(root, "product/inference/gpu/runtimes.json");
  const pinsPath = resolve(
    root,
    "infra/environments/prod/us-east-1/kubernetes/gpu-inference/pins.json",
  );
  const read = (path) => JSON.parse(readFileSync(path, "utf8"));
  const result = stageCanary({
    models: read(modelsPath),
    runtimes: read(runtimesPath),
    pins: read(pinsPath),
    release: read(positional[0]),
    expectedSource: positional[1],
    promote,
  });
  if (write) {
    writeFileSync(
      runtimesPath,
      JSON.stringify(result.runtimes, null, 2) + "\n",
    );
    writeFileSync(modelsPath, JSON.stringify(result.models, null, 2) + "\n");
  }
  console.log(
    JSON.stringify(
      {
        write,
        model: result.models[plan.name],
        runtime: result.runtimes[result.models[plan.name].runtime],
        next: "python3 tools/gpu/render-config.py && node tools/models/model-replica-rules.mjs; review and commit only generated canary/catalog changes",
      },
      null,
      2,
    ),
  );
}
