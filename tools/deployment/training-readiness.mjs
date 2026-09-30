import { execFileSync } from "node:child_process";
import { pathToFileURL } from "node:url";

const executor = (config, deployment) => {
  const override = deployment.spec.template.spec.containers[0].env?.find(
    (entry) => entry.name === "TRAINING_EXECUTOR",
  );
  if (override?.valueFrom)
    throw new Error("Training executor must be explicit");
  return override?.value ?? config.data?.TRAINING_EXECUTOR;
};

export const checkTrainingReadiness = ({
  apiConfig,
  apiDeployment,
  workerConfig,
  workerDeployment,
  pods,
  productImage,
  requireReady = false,
}) => {
  const apiExecutor = executor(apiConfig, apiDeployment);
  const workerExecutor = executor(workerConfig, workerDeployment);
  for (const value of [apiExecutor, workerExecutor]) {
    if (value && value !== "qwen-sft")
      throw new Error("Production training requires the qwen-sft executor");
  }
  const replicas = workerDeployment.spec.replicas ?? 1;
  if (!replicas && !apiExecutor && !requireReady) return "disabled";
  if (replicas < 1 || workerExecutor !== "qwen-sft")
    throw new Error(
      "Training requires a configured worker with nonzero replicas",
    );

  const status = workerDeployment.status ?? {};
  if (
    status.observedGeneration !== workerDeployment.metadata.generation ||
    status.updatedReplicas !== replicas ||
    (status.readyReplicas ?? 0) < replicas ||
    (status.availableReplicas ?? 0) < replicas
  )
    throw new Error("Temporal worker rollout is not ready");

  const ready = pods.items.filter((pod) => {
    if (pod.metadata.deletionTimestamp) return false;
    const container = pod.spec.containers.find(
      (entry) => entry.name === "temporal-worker",
    );
    const containerStatus = pod.status?.containerStatuses?.find(
      (entry) => entry.name === "temporal-worker",
    );
    return (
      container?.image === productImage &&
      containerStatus?.ready === true &&
      pod.status?.conditions?.some(
        (condition) =>
          condition.type === "Ready" && condition.status === "True",
      )
    );
  });
  if (ready.length < replicas)
    throw new Error(
      "Ready Temporal pods do not match the released product image",
    );
  return "ready";
};

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  const get = (kind, name, extra = []) =>
    JSON.parse(
      execFileSync(
        "kubectl",
        [
          "--request-timeout=20s",
          "-n",
          "gradiated",
          "get",
          kind,
          ...(name ? [name] : []),
          ...extra,
          "-o",
          "json",
        ],
        {
          encoding: "utf8",
          timeout: 30_000,
          stdio: ["ignore", "pipe", "pipe"],
        },
      ),
    );
  try {
    const productImage =
      process.env.PRODUCT_IMAGE ??
      get("configmap", "gradiated-release").data.productImage;
    const result = checkTrainingReadiness({
      apiConfig: get("configmap", "api"),
      apiDeployment: get("deployment", "api"),
      workerConfig: get("configmap", "temporal-worker"),
      workerDeployment: get("deployment", "temporal-worker"),
      pods: get("pods", "", ["-l", "app.kubernetes.io/name=temporal-worker"]),
      productImage,
      requireReady: process.argv.includes("--require-ready"),
    });
    console.log(`Production training: ${result}`);
  } catch (error) {
    console.error(
      error.status === undefined
        ? error.message
        : "Unable to read training deployment state",
    );
    process.exitCode = 1;
  }
}
