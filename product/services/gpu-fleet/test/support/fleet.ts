import { createServer, type IncomingMessage, type Server } from "node:http";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { GPU_HOSTS } from "../../src/hosts.js";

export const FIRST = "01a0f19d-1ff3-7613-8cbf-81b693c0f0d4";
export const SECOND = "01a0fbf7-5276-700b-903b-7e04da150ed6";

export const gpuHost = (instanceId: string, podId: string) => ({
  apiVersion: "fleet.gradiated.com/v1alpha1",
  kind: "GpuHost",
  metadata: { name: `gpu-${instanceId}` },
  spec: {
    instanceId,
    provider: { name: "runpod", accountId: "user_test", podId },
    inventory: { gpuProduct: "B300", gpuCount: 4, cpu: 64, memoryGiB: 896 },
    managementSecret: { key: `gradiated/prod/platform/gpu-host/${instanceId}` },
  },
});

export const hostPath = (instanceId: string) =>
  `${GPU_HOSTS}/gpu-${instanceId}`;

const body = (request: IncomingMessage) =>
  new Promise<string>((resolve) => {
    let text = "";
    request.on("data", (chunk) => (text += chunk));
    request.on("end", () => resolve(text));
  });

/**
 * Host agents on loopback, one path per instance, answering ping the way
 * product/inference/gpu/host-agent.py does: 403 without the right bearer key.
 * `down` makes an instance stop answering; `identity` makes it claim another
 * instance ID.
 */
export const fakeHostAgents = async () => {
  const keys = await mkdtemp(path.join(tmpdir(), "gpu-fleet-keys-"));
  const down = new Set<string>();
  const identity = new Map<string, string>();
  // Ping fields that differ from a host running bundle bbbb… with no trial.
  const version = new Map<string, Record<string, unknown>>();
  const requests: { instanceId: string; body: unknown }[] = [];
  const server: Server = createServer(async (request, response) => {
    const instanceId = (request.url ?? "").split("/")[1] ?? "";
    const text = await body(request);
    // A gone host never answers; the request waits for the client's timeout.
    if (down.has(instanceId)) return;
    if (request.headers.authorization !== `Bearer key-${instanceId}`) {
      response.statusCode = 403;
      return response.end();
    }
    requests.push({ instanceId, body: JSON.parse(text) });
    response.setHeader("content-type", "application/json");
    response.end(
      JSON.stringify({
        instance_id: identity.get(instanceId) ?? instanceId,
        epoch: 7,
        host_bundle_sha256: "b".repeat(64),
        previous_host_bundle_sha256: "",
        host_bundle_trial: false,
        host_bundle_failed_sha256: "",
        host_launcher: true,
        host_bundle_staging_failed_sha256: "",
        ...version.get(instanceId),
      }),
    );
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address() as { port: number };

  return {
    keys,
    down,
    identity,
    version,
    requests,
    endpoint: (instanceId: string) =>
      `http://127.0.0.1:${port}/${instanceId}/_kubelet`,
    addKey: (instanceId: string) =>
      writeFile(path.join(keys, instanceId), `key-${instanceId}\n`),
    close: async () => {
      server.closeAllConnections();
      await new Promise<void>((resolve) => server.close(() => resolve()));
      await rm(keys, { recursive: true, force: true });
    },
  };
};
