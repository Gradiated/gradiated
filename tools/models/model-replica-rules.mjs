import { existsSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");

const target = resolve(
  root,
  "infra/environments/prod/us-east-1/kubernetes/workloads/observability/model-replica-rules.yaml",
);
export const modelReplicaRules = (resources) => {
  const rules = [];
  const models = new Set();
  const rollouts = resources.filter((resource) => resource?.kind === "Rollout");
  const autoscalers = new Map(
    resources
      .filter(
        (resource) =>
          resource?.kind === "ScaledObject" &&
          resource.spec?.scaleTargetRef?.kind === "Rollout",
      )
      .map((resource) => [resource.spec.scaleTargetRef.name, resource]),
  );
  const requestedReplicas = (resource) => {
    const scaler = autoscalers.get(resource.metadata.name);
    const paused =
      scaler?.metadata?.annotations?.["autoscaling.keda.sh/paused-replicas"];
    if (
      paused !== undefined &&
      (typeof paused !== "string" ||
        !/^(0|[1-9][0-9]*)$/.test(paused) ||
        !Number.isSafeInteger(Number(paused)))
    )
      throw new Error("Invalid paused replica annotation");
    return {
      scaler,
      paused,
      requested: paused === undefined ? resource.spec.replicas : Number(paused),
    };
  };
  for (const resource of resources) {
    if (resource?.kind !== "Rollout") continue;
    const annotations = resource.spec?.template?.metadata?.annotations ?? {};
    const model =
      annotations["gradiated.com/serving-model-id"] ??
      annotations["gradiated.com/model-id"];
    const count = resource.spec?.replicas;
    if (
      typeof model !== "string" ||
      !model ||
      !Number.isSafeInteger(count) ||
      count < 0
    )
      throw new Error("Rollout has invalid model identity or replica count");
    const canary = Object.hasOwn(annotations, "gradiated.com/canary-of");
    const mode = annotations["gradiated.com/serving-mode"] ?? "production";
    if (
      Object.hasOwn(annotations, "gradiated.com/serving-model-id") &&
      !Object.hasOwn(annotations, "gradiated.com/serving-mode")
    )
      throw new Error("A mapped serving model requires an explicit mode");
    if (
      !["production", "qualification"].includes(mode) ||
      (!canary &&
        (mode === "qualification" ||
          Object.hasOwn(annotations, "gradiated.com/serving-model-id")))
    )
      throw new Error("Invalid qualification mode or serving model mapping");
    if (canary) {
      const parent = annotations["gradiated.com/canary-of"];
      const matches = rollouts.filter((item) => item.metadata.name === parent);
      const primary = matches[0];
      if (
        typeof parent !== "string" ||
        matches.length !== 1 ||
        parent === resource.metadata.name ||
        (primary.spec.template.metadata.annotations[
          "gradiated.com/serving-model-id"
        ] ??
          primary.spec.template.metadata.annotations[
            "gradiated.com/model-id"
          ]) !== model ||
        Object.hasOwn(
          primary.spec.template.metadata.annotations,
          "gradiated.com/canary-of",
        )
      )
        throw new Error("Invalid canary relationship or model identity");
    } else {
      if (models.has(model))
        throw new Error(
          "Rollout has duplicate model identity without an explicit canary relationship",
        );
      models.add(model);
    }
    const { scaler, paused, requested } = requestedReplicas(resource);
    const isolated = mode === "qualification";
    // A production replacement becomes the serving floor once its primary is
    // intentionally scaled to zero. Qualification-only capacity never counts.
    const retiredPrimary =
      canary &&
      requestedReplicas(
        rollouts.find(
          (item) =>
            item.metadata.name === annotations["gradiated.com/canary-of"],
        ),
      ).requested === 0;
    const productionReplacements = retiredPrimary
      ? rollouts.filter((item) => {
          const metadata = item.spec.template.metadata.annotations;
          return (
            metadata["gradiated.com/canary-of"] ===
              annotations["gradiated.com/canary-of"] &&
            (metadata["gradiated.com/serving-mode"] ?? "production") ===
              "production" &&
            requestedReplicas(item).requested > 0
          );
        })
      : [];
    let minimum = isolated || (canary && !retiredPrimary) ? 0 : requested;
    if (!isolated && productionReplacements.length > 1) {
      // Split production pools preserve their reviewed aggregate availability
      // budget while an additional replacement warms up. A sole replacement
      // continues to carry the full serving floor even without a PDB.
      const budget = resources.find(
        (item) =>
          item?.kind === "PodDisruptionBudget" &&
          item.metadata.name === resource.metadata.name,
      );
      if (budget) {
        const floor = budget.spec?.minAvailable;
        if (!Number.isSafeInteger(floor) || floor < 0 || floor > requested)
          throw new Error("Invalid production replacement disruption floor");
        minimum = floor;
      }
    }
    const expr = isolated
      ? "vector(0)"
      : paused !== undefined
        ? `vector(${requested})`
        : scaler
          ? `max(kube_horizontalpodautoscaler_status_desired_replicas{namespace="${scaler.metadata.namespace}",horizontalpodautoscaler="keda-hpa-${scaler.metadata.name}"}) or vector(${count})`
          : `vector(${count})`;
    rules.push(
      {
        record: "gradiated_model_desired_replicas",
        expr,
        labels: { model, rollout: resource.metadata.name },
      },
      {
        record: "gradiated_model_minimum_replicas",
        expr: `vector(${minimum})`,
        labels: { model, rollout: resource.metadata.name },
      },
    );
  }
  if (!rules.length)
    throw new Error(
      "No model Rollouts found; refusing to erase desired replicas",
    );
  return {
    apiVersion: "monitoring.coreos.com/v1",
    kind: "PrometheusRule",
    metadata: {
      name: "gradiated-model-replicas",
      labels: { release: "observability" },
      annotations: {
        "gradiated.com/generated-by":
          "node tools/models/model-replica-rules.mjs",
      },
    },
    spec: { groups: [{ name: "gradiated.models.desired", rules }] },
  };
};
if (
  process.argv[1] &&
  pathToFileURL(resolve(process.argv[1])).href === import.meta.url
) {
  const { parseAllDocuments } = createRequire(
    resolve(root, "product/package.json"),
  )("yaml");
  // Each model is rendered into gpu-inference/models/<model>/<model>.yaml.
  const directory = resolve(
    root,
    "infra/environments/prod/us-east-1/kubernetes/gpu-inference/models",
  );
  const resources = readdirSync(directory)
    .sort()
    .map((model) => resolve(directory, model, `${model}.yaml`))
    .filter(existsSync)
    .flatMap((file) =>
      parseAllDocuments(readFileSync(file, "utf8")).map((doc) => doc.toJS()),
    );
  const content = JSON.stringify(modelReplicaRules(resources), null, 2) + "\n";
  if (process.argv.includes("--check")) {
    if (readFileSync(target, "utf8") !== content)
      throw new Error(
        "Model replica rules are stale; run node tools/models/model-replica-rules.mjs",
      );
  } else writeFileSync(target, content);
}
