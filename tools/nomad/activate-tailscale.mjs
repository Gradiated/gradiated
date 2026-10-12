import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { parseArgs } from "node:util";
import { randomUUID } from "node:crypto";
import { pathToFileURL } from "node:url";
import { setTimeout as delay } from "node:timers/promises";

const execute = promisify(execFile);

export const inferenceReady = (object, kind, pods) => {
  const replicas = object.spec.replicas;
  const condition = kind === "peerrelay" ? "PeerRelayReady" : "ProxyGroupReady";
  const readyPods = pods.items.filter(
    (pod) =>
      !pod.metadata.deletionTimestamp &&
      pod.status?.conditions?.some(
        (c) => c.type === "Ready" && c.status === "True",
      ),
  );
  if (
    !Number.isInteger(replicas) ||
    replicas < 3 ||
    !object.status?.conditions?.some(
      (c) =>
        c.type === condition &&
        c.status === "True" &&
        c.observedGeneration === object.metadata.generation,
    ) ||
    new Set(readyPods.map((pod) => pod.metadata.name)).size < replicas ||
    new Set(readyPods.map((pod) => pod.spec?.nodeName).filter(Boolean)).size <
      replicas
  )
    return false;

  if (kind !== "peerrelay") return true;

  const endpoints = new Set(
    (object.status.endpoints ?? [])
      .filter(
        (endpoint) =>
          typeof endpoint.address === "string" &&
          endpoint.address.length > 0 &&
          Number.isInteger(endpoint.port) &&
          endpoint.port > 0 &&
          endpoint.port <= 65535,
      )
      .map((endpoint) => endpoint.replica),
  );
  return Array.from({ length: replicas }, (_, index) => index).every((index) =>
    endpoints.has(index),
  );
};

export const waitForQualification = async (
  getJob,
  { pause = delay, now = Date.now, timeoutMs = 360_000 } = {},
) => {
  const deadline = now() + timeoutMs;
  while (now() < deadline) {
    const job = await getJob();
    const conditions = job.status?.conditions ?? [];
    if (
      conditions.some(
        (c) =>
          ["Failed", "FailureTarget"].includes(c.type) && c.status === "True",
      )
    )
      throw new Error("Qualification Job failed; do not close public ingress");

    if (conditions.some((c) => c.type === "Complete" && c.status === "True"))
      return;

    await pause(Math.min(2000, Math.max(0, deadline - now())));
  }
  throw new Error(
    "Qualification Job timed out; inspect its result before changing ingress",
  );
};
export const qualificationJob = (
  instanceId,
  image,
  apply = false,
) => {
  if (
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(
      instanceId,
    )
  )
    throw new Error("A canonical instance UUID is required");
  if (
    !/^873716897517[.]dkr[.]ecr[.]us-east-1[.]amazonaws[.]com\/gradiated\/prod\/product@sha256:[a-f0-9]{64}$/.test(
      image,
    )
  )
    throw new Error("Use an immutable product image");
  return {
    apiVersion: "batch/v1",
    kind: "Job",
    metadata: {
      name: `private-serving-${instanceId.slice(0, 8)}-${randomUUID().slice(0, 8)}`,
      namespace: "gradiated",
    },
    spec: {
      backoffLimit: 0,
      activeDeadlineSeconds: 300,
      ttlSecondsAfterFinished: 600,
      template: {
        metadata: {
          labels: { "app.kubernetes.io/name": "private-serving-qualification" },
        },
        spec: {
          restartPolicy: "Never",
          automountServiceAccountToken: false,
          securityContext: {
            runAsNonRoot: true,
            runAsUser: 1000,
            seccompProfile: { type: "RuntimeDefault" },
          },
          containers: [
            {
              name: "qualify",
              image,
              command: ["node", "scripts/set-private-serving.mjs"],
              args: [
                "--instance-id",
                instanceId,
                ...(apply ? ["--apply"] : []),
              ],
              env: [
                {
                  name: "DATABASE_URL",
                  valueFrom: {
                    secretKeyRef: { name: "worker", key: "DATABASE_URL" },
                  },
                },

              ],
              resources: {
                requests: { cpu: "100m", memory: "256Mi" },
                limits: { cpu: "1", memory: "512Mi" },
              },
              securityContext: {
                allowPrivilegeEscalation: false,
                readOnlyRootFilesystem: true,
                capabilities: { drop: ["ALL"] },
              },
            },
          ],
        },
      },
    },
  };
};

const main = async () => {
  const { values } = parseArgs({
    options: {
      "instance-id": { type: "string" },
      image: { type: "string" },
      apply: { type: "boolean", default: false },
    },
  });
  if (!values["instance-id"] || !values.image)
    throw new Error("instance-id and image are required");
  for (const [resource, name] of [
        ["proxygroup", "inference-egress"],
        ["peerrelay", "tailscale-relay"],
      ]) {
    const { stdout } = await execute(
      "kubectl",
      ["get", resource, name, "-o", "json"],
      { timeout: 30_000 },
    );
    const object = JSON.parse(stdout);
    const role = resource === "proxygroup" ? "egress" : "relay";
    const { stdout: podState } = await execute(
      "kubectl",
      [
        "get",
        "pods",
        "-n",
        "tailscale-inference",
        "-l",
        `gradiated.com/tailscale-role=${role}`,
        "-o",
        "json",
      ],
      { timeout: 30_000 },
    );
    if (!inferenceReady(object, resource, JSON.parse(podState))) {
      throw new Error(
        `${resource} must have three ready replicas at its current generation`,
      );
    }
  }
  const job = qualificationJob(
    values["instance-id"],
    values.image,
    values.apply,
  );
  const child = execute("kubectl", ["create", "-f", "-"], { timeout: 30_000 });
  child.child.stdin.end(JSON.stringify(job));
  await child;
  console.log(
    `Created ${job.metadata.namespace}/${job.metadata.name}; waiting for qualification`,
  );
  await waitForQualification(async () => {
    const { stdout } = await execute(
      "kubectl",
      [
        "get",
        "job",
        job.metadata.name,
        "-n",
        job.metadata.namespace,
        "-o",
        "json",
      ],
      { timeout: 10_000 },
    );
    return JSON.parse(stdout);
  });
  console.log(
    `Completed ${job.metadata.namespace}/${job.metadata.name}; verify gateway projection before changing ingress`,
  );
};

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  main().catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
}
