import { execFileSync } from "node:child_process";
import { pathToFileURL } from "node:url";

// workloadRef templates can update before the Rollout observes them. A stale
// Healthy status must never qualify a newly recorded image.
export function rolloutReady(rollout, deployment) {
  const { spec, status = {} } = rollout;
  if (
    String(status.workloadObservedGeneration) !==
      String(deployment.metadata.generation) ||
    String(status.observedGeneration) !== String(rollout.metadata.generation)
  )
    return false;
  if (status.abort || status.phase === "Degraded") {
    throw new Error(
      `${rollout.metadata.name}: rollout aborted; stable version retained`,
    );
  }
  const desired = spec.replicas ?? 1;
  return (
    desired > 0 &&
    status.phase === "Healthy" &&
    !!status.currentPodHash &&
    status.stableRS === status.currentPodHash &&
    status.updatedReplicas === desired &&
    (status.availableReplicas ?? 0) >= desired
  );
}

export async function waitRollouts({
  read,
  now = Date.now,
  wait = () => new Promise((r) => setTimeout(r, 10000)),
}) {
  const services = ["api", "gateway", "proxy"];
  const deadline = now() + 20 * 60 * 1000;
  // An earlier healthy service can regress while another is still progressing.
  while (true) {
    const pending = [];
    for (const name of services) {
      let rollout, deployment;
      try {
        rollout = await read("rollouts.argoproj.io", name);
        deployment = await read("deployment", name);
      } catch {
        // Argo may still be creating the Rollout, or the API may be temporarily unavailable.
        pending.push(name);
        continue;
      }
      if (!rolloutReady(rollout, deployment)) pending.push(name);
    }
    if (!pending.length) {
      console.log("API, gateway and proxy: current workloads fully promoted");
      return;
    }
    if (now() >= deadline)
      throw new Error(`Rollouts did not complete: ${pending.join(", ")}`);
    await wait();
  }
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  await waitRollouts({
    read: (kind, name) =>
      JSON.parse(
        execFileSync(
          "kubectl",
          [
            "--request-timeout=20s",
            "-n",
            "gradiated",
            "get",
            kind,
            name,
            "-o",
            "json",
          ],
          {
            encoding: "utf8",
            timeout: 30000,
            stdio: ["ignore", "pipe", "pipe"],
          },
        ),
      ),
  });
}
