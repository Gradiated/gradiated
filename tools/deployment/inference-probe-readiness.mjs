import { execFile, execFileSync } from "node:child_process";
import { pathToFileURL } from "node:url";
import { promisify } from "node:util";

export const checkInferenceProbeReadiness = (
  observations,
  now = Date.now() / 1000,
) => {
  const targets = new Map();
  const successes = new Map();
  let inventory = 0;
  for (const observation of observations) {
    for (const { id, modelId } of observation.deployments)
      targets.set(id, modelId);
    for (const line of observation.metrics.split("\n")) {
      const sample = line.match(
        /^(gradiated_inference_probe_\w+)(?:\{(.*)\})? ([\d.e+-]+)$/,
      );
      if (!sample) continue;

      const [, metric, labels, value] = sample;
      if (metric === "gradiated_inference_probe_inventory_timestamp_seconds")
        inventory = Math.max(inventory, Number(value));
      if (metric !== "gradiated_inference_probe_last_success_timestamp_seconds")
        continue;

      const id = labels?.match(/(?:^|,)deployment="([^"]+)"/)?.[1];
      if (id)
        successes.set(id, Math.max(successes.get(id) ?? 0, Number(value)));
    }
  }
  if (!inventory || now - inventory > 10)
    throw new Error("Probe discovery is not fresh");
  if (!targets.size)
    throw new Error("No serving inference deployments discovered");
  const result = new Map();
  for (const [id, model] of targets) {
    const timestamp = successes.get(id) ?? 0;
    if (!timestamp || now - timestamp > 75)
      throw new Error(
        `No fresh successful public inference for ${model} on ${id}`,
      );
    result.set(id, timestamp);
  }
  return result;
};

export const readInferenceProbeObservations = async (pods, read) => {
  if (!pods.length) throw new Error("No ready workers discovered");

  const path = (pod, endpoint) =>
    `/api/v1/namespaces/gradiated/pods/http:${encodeURIComponent(pod.metadata.name)}:9464/proxy${endpoint}`;
  const deployments = JSON.parse(
    await read(path(pods[0], "/metrics/targets/inference")),
  );
  if (
    !Array.isArray(deployments) ||
    deployments.some(
      (deployment) =>
        typeof deployment?.id !== "string" ||
        !deployment.id ||
        typeof deployment.modelId !== "string" ||
        !deployment.modelId,
    )
  )
    throw new Error("Invalid serving inference inventory");

  return Promise.all(
    pods.map(async (pod) => ({
      deployments,
      metrics: await read(path(pod, "/metrics")),
    })),
  );
};

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  const kubectl = (...args) =>
    execFileSync(
      "kubectl",
      ["--request-timeout=20s", "-n", "gradiated", ...args],
      {
        encoding: "utf8",
        timeout: 25_000,
      },
    );
  const execute = promisify(execFile);
  const deadline = Date.now() + 120_000;
  let previous = new Map();
  let consecutive = 0;
  while (Date.now() < deadline) {
    try {
      const pods = JSON.parse(
        kubectl(
          "get",
          "pods",
          "-l",
          "app.kubernetes.io/name=worker",
          "-o",
          "json",
        ),
      );
      const readyPods = pods.items.filter(
        (pod) =>
          !pod.metadata.deletionTimestamp &&
          pod.status?.containerStatuses?.some(
            (container) => container.name === "worker" && container.ready,
          ),
      );
      const observations = await readInferenceProbeObservations(
        readyPods,
        async (path) => {
          const { stdout } = await execute(
            "kubectl",
            ["--request-timeout=20s", "-n", "gradiated", "get", "--raw", path],
            {
              encoding: "utf8",
              timeout: Math.max(1, Math.min(25_000, deadline - Date.now())),
            },
          );
          return stdout;
        },
      );
      const current = checkInferenceProbeReadiness(observations);
      const stable =
        previous.size === current.size &&
        [...current].every(
          ([id, timestamp]) => previous.has(id) && timestamp >= previous.get(id),
        );
      consecutive = stable ? consecutive + 1 : 1;
      previous = current;
      console.log(
        `Public inference probes: ${current.size} serving deployments, ${consecutive}/3 fresh samples`,
      );
      if (consecutive >= 3) process.exit(0);
    } catch (error) {
      console.error(
        error instanceof Error ? error.message : "Inference probe check failed",
      );
      consecutive = 0;
      previous = new Map();
    }
    await new Promise((resolve) => setTimeout(resolve, 5000));
  }
  throw new Error(
    "Public inference probes did not become healthy within two minutes",
  );
}
