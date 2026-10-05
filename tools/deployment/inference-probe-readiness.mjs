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
    if (!timestamp || now - timestamp > 10)
      throw new Error(
        `No fresh successful public inference for ${model} on ${id}`,
      );
    result.set(id, timestamp);
  }
  return result;
};

const readWorker = `
import { createControlDatabase, createNomadDeploymentStore } from '@gradiated/control';
const { database, pool } = createControlDatabase(process.env.DATABASE_URL, 1);
try {
  const deployments = (await createNomadDeploymentStore(database).replicas())
    .map(({ id, modelId }) => ({ id, modelId }));
  const response = await fetch('http://127.0.0.1:9464/metrics', { signal: AbortSignal.timeout(4000) });
  if (!response.ok) throw new Error('Worker metrics unavailable');
  console.log(JSON.stringify({ deployments, metrics: await response.text() }));
} finally { await pool.end(); }
`;

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
      const observations = await Promise.all(
        readyPods.map(async (pod) => {
          const { stdout } = await execute(
            "kubectl",
            [
              "--request-timeout=20s",
              "-n",
              "gradiated",
              "exec",
              pod.metadata.name,
              "-c",
              "worker",
              "--",
              "node",
              "--input-type=module",
              "-e",
              readWorker,
            ],
            {
              encoding: "utf8",
              timeout: Math.max(1, Math.min(25_000, deadline - Date.now())),
            },
          );
          return JSON.parse(stdout);
        }),
      );
      const current = checkInferenceProbeReadiness(observations);
      const advancing =
        previous.size === current.size &&
        [...current].every(
          ([id, timestamp]) => previous.has(id) && timestamp > previous.get(id),
        );
      consecutive = advancing ? consecutive + 1 : 1;
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
