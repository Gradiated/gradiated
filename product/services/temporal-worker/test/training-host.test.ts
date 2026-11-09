import { randomUUID } from "node:crypto";
import { expect, it, vi } from "vitest";
import {
  createTrainingHosts,
  trainingHostJob,
} from "../src/training/kubernetes-host.js";
const runId = randomUUID();
const nodeId = randomUUID();
const allocationId = randomUUID();
const config = {
  bundleUrl: `s3::https://test.s3.us-east-1.amazonaws.com/bundles/sha256/${"a".repeat(64)}.tar.gz`,
  bundleSha256: "a".repeat(64),
  baseId: "base-test",
  gpuType: "B300",
};
const nodes = [
  {
    nodeId,
    podId: "pod1",
    url: `http://gpu-${nodeId}.tailscale-inference.svc.cluster.local:8888`,
  },
];
const pod = (phase = "Running", ready = true) => ({
  metadata: { uid: allocationId },
  spec: { nodeName: `gpu-${nodeId}` },
  status: {
    phase,
    conditions: [{ type: "Ready", status: ready ? "True" : "False" }],
  },
});
it("keeps placement inside the registered pool and transfers no cluster credentials", () => {
  const job = trainingHostJob(runId, 1, nodes, config);
  const spec = job.spec.template.spec;
  expect(
    spec.affinity.nodeAffinity.requiredDuringSchedulingIgnoredDuringExecution
      .nodeSelectorTerms[0]!.matchExpressions[0]!.values,
  ).toEqual([nodeId]);
  expect(spec.automountServiceAccountToken).toBe(false);
  expect(spec.restartPolicy).toBe("Never");
  expect(spec.priorityClassName).toBe("gpu-training");
  expect(spec.tolerations).toContainEqual({
    key: "gradiated.com/reserved",
    operator: "Equal",
    value: "training",
    effect: "NoSchedule",
  });
  expect(job.spec.backoffLimit).toBe(0);
  expect(JSON.stringify(job)).not.toMatch(
    /DATABASE|TEMPORAL|secretKeyRef|envFrom/,
  );
});
it("reserves tensor-parallel training within one node", () => {
  const job = trainingHostJob(runId, 1, nodes, {
    ...config,
    recipe: { model: "glm", gpu_count: 4 },
  });
  expect(job.spec.template.spec.containers[0]!.resources.requests).toEqual({
    cpu: "16",
    memory: "256Gi",
    "nvidia.com/gpu": "4",
  });
  expect(() =>
    trainingHostJob(runId, 1, nodes, { ...config, recipe: { gpu_count: 0 } }),
  ).toThrow();
});
it.each([false, true])(
  "releases the complete run with foreground cleanup; failure: %s",
  async (fails) => {
    const request = vi.fn(async () => {
      if (fails) throw new Error("API unavailable");
      return {};
    });
    const hosts = createTrainingHosts({
      request,
      nodes: async () => nodes,
      config,
    });
    if (fails)
      await expect(hosts.release(runId)).rejects.toThrow("API unavailable");
    else await hosts.release(runId);
    expect(request).toHaveBeenCalledWith(
      expect.stringContaining(
        encodeURIComponent(`gradiated.com/training-run=${runId}`),
      ),
      "DELETE",
      expect.objectContaining({ propagationPolicy: "Foreground" }),
    );
  },
);
it("creates a missing Job once and waits for scheduling without blocking an activity", async () => {
  const request = vi.fn(async (path: string, method?: string) => {
    if (path.endsWith(`/training-${runId}-1`) && !method)
      throw Object.assign(new Error("missing"), { code: "404" });
    return path.includes("pods?") ? { items: [] } : {};
  });
  const hosts = createTrainingHosts({
    request,
    nodes: async () => nodes,
    config,
  });
  expect(await hosts.allocate(runId, 1)).toBeNull();
  expect(request.mock.calls.filter((c) => c[1] === "POST")).toHaveLength(1);
});
it("uses a ready pod UID and the registered private serving URL", async () => {
  const request = async (path: string) =>
    path.includes("pods?") ? { items: [pod()] } : {};
  const http = vi.fn(async () => Response.json({ renewed: true }));
  const hosts = createTrainingHosts({
    request,
    nodes: async () => nodes,
    config,
    fetch: http,
  });
  expect(await hosts.allocate(runId, 1)).toEqual({
    allocationId,
    jobId: `training-${runId}-1`,
    url: `${nodes[0]!.url}/alloc/${allocationId}`,
  });
  expect(http.mock.calls[0]).toBeDefined();
});
it.each(["Failed", "Succeeded"])(
  "rejects an exited %s allocation without replacing it",
  async (phase) => {
    const request = async (path: string) =>
      path.includes("pods?") ? { items: [pod(phase)] } : {};
    await expect(
      createTrainingHosts({
        request,
        nodes: async () => nodes,
        config,
      }).allocate(runId, 1),
    ).rejects.toThrow("allocation failed");
  },
);
it("does not renew an unready or different pod", async () => {
  const http = vi.fn(async () => Response.json({ renewed: true }));
  const hosts = createTrainingHosts({
    request: async () => ({ items: [pod("Running", false)] }),
    nodes: async () => nodes,
    config,
    fetch: http,
  });
  await expect(
    hosts.renew({ allocationId, jobId: "job", url: nodes[0]!.url }),
  ).rejects.toThrow("no longer ready");
  expect(http).not.toHaveBeenCalled();
});
it("rejects allocations outside the assigned node pool", async () => {
  const other = pod();
  other.spec.nodeName = "gpu-" + randomUUID();
  const request = async (path: string) =>
    path.includes("pods?") ? { items: [other] } : {};
  await expect(
    createTrainingHosts({ request, nodes: async () => nodes, config }).allocate(
      runId,
      1,
    ),
  ).rejects.toThrow("outside its pool");
});
it("waits when no registered capacity is available", async () => {
  const request = vi.fn(async () => ({}));
  expect(
    await createTrainingHosts({
      request,
      nodes: async () => [],
      config,
    }).allocate(runId, 1),
  ).toBeNull();
  expect(request).not.toHaveBeenCalled();
});
const retryHost = {
  allocationId,
  jobId: `training-${runId}-1`,
  url: "https://trainer.test",
};
const hostsWithHttp = (http: typeof fetch, signal?: AbortSignal) =>
  createTrainingHosts({
    request: async () => ({}),
    nodes: async () => [],
    config,
    fetch: http,
    ...(signal ? { signal: () => signal } : {}),
  });

it.each([undefined, { id: "train-1", operation: "train" }])(
  "retries transient HTTP errors with the same request: %j",
  async (command) => {
    const http = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(null, { status: 502 }))
      .mockResolvedValueOnce(Response.json({ ready: true }));
    const hosts = hostsWithHttp(http);
    await expect(
      hosts.call(retryHost, "/operations", command),
    ).resolves.toEqual({ ready: true });
    expect(http).toHaveBeenCalledTimes(2);
    expect(http.mock.calls[0]).toEqual(http.mock.calls[1]);
  },
);

it("stops retrying after three server errors", async () => {
  const http = vi
    .fn<typeof fetch>()
    .mockImplementation(async () => new Response(null, { status: 503 }));
  await expect(hostsWithHttp(http).call(retryHost, "/health")).rejects.toThrow(
    "Trainer request failed (503).",
  );
  expect(http).toHaveBeenCalledTimes(3);
});

it("does not retry rejected commands", async () => {
  const http = vi
    .fn<typeof fetch>()
    .mockResolvedValue(new Response(null, { status: 409 }));
  await expect(
    hostsWithHttp(http).call(retryHost, "/operations", { id: "train-2" }),
  ).rejects.toThrow("Trainer request failed (409).");
  expect(http).toHaveBeenCalledTimes(1);
});

it("cancels retry backoff when the activity is cancelled", async () => {
  const controller = new AbortController();
  const http = vi.fn<typeof fetch>().mockImplementation(async () => {
    controller.abort();
    return new Response(null, { status: 502 });
  });
  await expect(
    hostsWithHttp(http, controller.signal).call(retryHost, "/health"),
  ).rejects.toMatchObject({ name: "AbortError" });
  expect(http).toHaveBeenCalledTimes(1);
});

it("retries a lost operation reply with the identical command", async () => {
  const http = vi
    .fn<typeof fetch>()
    .mockRejectedValueOnce(new TypeError("fetch failed"))
    .mockResolvedValueOnce(
      Response.json({ id: "train-transport", status: "running" }),
    );
  await expect(
    hostsWithHttp(http).call(retryHost, "/operations", {
      id: "train-transport",
      operation: "train",
    }),
  ).resolves.toEqual({ id: "train-transport", status: "running" });
  expect(http).toHaveBeenCalledTimes(2);
  expect(http.mock.calls[0]).toEqual(http.mock.calls[1]);
});

it("bounds transport retries and preserves the final error", async () => {
  const error = new TypeError("fetch failed");
  const http = vi.fn<typeof fetch>().mockRejectedValue(error);
  await expect(hostsWithHttp(http).call(retryHost, "/health")).rejects.toBe(
    error,
  );
  expect(http).toHaveBeenCalledTimes(3);
});

it("does not retry transport failures after activity cancellation", async () => {
  const controller = new AbortController();
  const error = new TypeError("fetch failed");
  const http = vi.fn<typeof fetch>().mockImplementation(async () => {
    controller.abort();
    throw error;
  });
  await expect(
    hostsWithHttp(http, controller.signal).call(retryHost, "/health"),
  ).rejects.toBe(error);
  expect(http).toHaveBeenCalledTimes(1);
});
