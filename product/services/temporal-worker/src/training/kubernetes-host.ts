import { setTimeout as delay } from "node:timers/promises";
import { z } from "zod";
import type { createKubernetesRequest } from "@gradiated/control";

export type KubernetesRequest = ReturnType<typeof createKubernetesRequest>;
export type TrainingHost = { allocationId: string; jobId: string; url: string };
export type TrainingNode = { nodeId: string; podId: string; url: string };
export type TrainingHostConfig = {
  bundleUrl: string;
  bundleSha256: string;
  baseId: string;
  gpuType: string;
  nodePool?: string | undefined;
  recipe?: Record<string, unknown> | undefined;
};
const namespace = "gpu-inference";
const jobsPath = `/apis/batch/v1/namespaces/${namespace}/jobs`;
const podsPath = `/api/v1/namespaces/${namespace}/pods`;
const pods = z.object({
  items: z.array(
    z.object({
      metadata: z.object({ uid: z.uuid() }),
      spec: z.object({ nodeName: z.string().optional() }),
      status: z
        .object({
          phase: z.string().optional(),
          conditions: z
            .array(z.object({ type: z.string(), status: z.string() }))
            .default([]),
        })
        .default({ conditions: [] }),
    }),
  ),
});

export const trainingHostJob = (
  runId: string,
  ordinal: number,
  nodes: TrainingNode[],
  config: TrainingHostConfig,
) => {
  z.uuid().parse(runId);
  z.number().int().min(1).parse(ordinal);
  z.array(
    z.object({
      nodeId: z.uuid(),
      podId: z.string().regex(/^[a-z0-9]+$/),
      url: z.string().url(),
    }),
  )
    .min(1)
    .max(4)
    .parse(nodes);
  z.string()
    .regex(/^[0-9a-f]{64}$/)
    .parse(config.bundleSha256);
  const gpuCount = z
    .number()
    .int()
    .min(1)
    .max(8)
    .parse(config.recipe?.gpu_count ?? 1);
  const name = `training-${runId}-${ordinal}`;
  const resources = {
    cpu: String(4 * gpuCount),
    memory: `${64 * gpuCount}Gi`,
    "nvidia.com/gpu": String(gpuCount),
  };
  return {
    apiVersion: "batch/v1",
    kind: "Job",
    metadata: {
      name,
      namespace,
      labels: { "gradiated.com/training-run": runId },
    },
    spec: {
      backoffLimit: 0,
      activeDeadlineSeconds: 86400,
      ttlSecondsAfterFinished: 3600,
      template: {
        metadata: {
          labels: { "gradiated.com/training-run": runId },
          annotations: {
            "gradiated.com/workload-kind": "training",
            "gradiated.com/model-id": "training",
            "gradiated.com/release": "{}",
            ...(config.recipe
              ? {
                  "gradiated.com/training-recipe": JSON.stringify(
                    config.recipe,
                  ),
                }
              : {}),
          },
        },
        spec: {
          serviceAccountName: "model-runtime",
          automountServiceAccountToken: false,
          priorityClassName: "gpu-training",
          restartPolicy: "Never",
          terminationGracePeriodSeconds: 90,
          nodeSelector: {
            "gradiated.com/provider": "runpod",
            "nvidia.com/gpu.product": config.gpuType,
          },
          affinity: {
            nodeAffinity: {
              requiredDuringSchedulingIgnoredDuringExecution: {
                nodeSelectorTerms: [
                  {
                    matchExpressions: [
                      {
                        key: "gradiated.com/instance-id",
                        operator: "In",
                        values: nodes.map((n) => n.nodeId),
                      },
                    ],
                  },
                ],
              },
            },
          },
          tolerations: [
            {
              key: "gradiated.com/gpu",
              operator: "Equal",
              value: "true",
              effect: "NoSchedule",
            },
          ],
          containers: [
            {
              name: "runtime",
              image: `gradiated/training-bundle@sha256:${config.bundleSha256}`,
              resources: { requests: resources, limits: resources },
            },
          ],
        },
      },
    },
  };
};

export const createTrainingHosts = (input: {
  request: KubernetesRequest;
  nodes: () => Promise<TrainingNode[]>;
  config: TrainingHostConfig;
  fetch?: typeof fetch;
  signal?: () => AbortSignal;
}) => {
  const request = input.request;
  const http = input.fetch ?? fetch;
  const allocations = async (jobId: string) =>
    pods.parse(
      await request(
        `${podsPath}?labelSelector=${encodeURIComponent(`job-name=${jobId}`)}`,
      ),
    ).items;
  const call = async (host: TrainingHost, path: string, command?: unknown) => {
    const signal = AbortSignal.any([
      AbortSignal.timeout(30_000),
      ...(input.signal ? [input.signal()] : []),
    ]);

    for (let attempt = 0; ; attempt++) {
      try {
        const response = await http(`${host.url}${path}`, {
          method: command === undefined ? "GET" : "POST",
          redirect: "error",
          headers: {
            "content-type": "application/json",
          },
          ...(command === undefined ? {} : { body: JSON.stringify(command) }),
          signal,
        });
        if (response.ok) return (await response.json()) as unknown;

        await response.body?.cancel();
        if (response.status < 500 || attempt === 2)
          throw new Error(`Trainer request failed (${response.status}).`);
      } catch (error) {
        // Fetch transport failures can lose a reply after an idempotent command lands.
        if (!(error instanceof TypeError) || signal.aborted || attempt === 2)
          throw error;
      }

      await delay(1000 * (attempt + 1), undefined, { signal });
    }
  };

  const renew = async (host: TrainingHost) => {
    const found = await allocations(host.jobId);
    const current = found.find((p) => p.metadata.uid === host.allocationId);
    if (
      current?.status.phase !== "Running" ||
      !current.status.conditions.some(
        (c) => c.type === "Ready" && c.status === "True",
      )
    )
      throw new Error("Training reservation is no longer ready.");
    z.object({ renewed: z.literal(true) }).parse(
      await call(host, "/reservation", { allocation_id: host.allocationId }),
    );
  };
  return {
    call,
    renew,
    async allocate(
      runId: string,
      ordinal: number,
      config = input.config,
    ): Promise<TrainingHost | null> {
      const nodes = await input.nodes();
      if (!nodes.length) return null;
      const job = trainingHostJob(runId, ordinal, nodes, config);
      try {
        await request(`${jobsPath}/${job.metadata.name}`);
      } catch (error) {
        if ((error as { code?: string }).code !== "404") throw error;
        try {
          await request(jobsPath, "POST", job);
        } catch (error) {
          if ((error as { code?: string }).code !== "409") throw error;
        }
      }
      const found = await allocations(job.metadata.name);
      if (
        found.some((p) =>
          ["Failed", "Succeeded"].includes(p.status.phase ?? ""),
        )
      )
        throw new Error("Training host allocation failed.");
      const running = found.filter((p) => p.status.phase === "Running");
      if (running.length > 1)
        throw new Error("Training host has duplicate allocations.");
      const current = running[0];
      if (!current) return null;
      const node = nodes.find(
        (n) => `gpu-${n.nodeId}` === current.spec.nodeName,
      );
      if (!node) throw new Error("Training allocation is outside its pool.");
      const host = {
        allocationId: current.metadata.uid,
        jobId: job.metadata.name,
        url: `${node.url}/alloc/${current.metadata.uid}`,
      };
      try {
        await renew(host);
        return host;
      } catch {
        return null;
      }
    },
    async release(runId: string) {
      z.uuid().parse(runId);
      await request(
        `${jobsPath}?labelSelector=${encodeURIComponent(`gradiated.com/training-run=${runId}`)}`,
        "DELETE",
        {
          apiVersion: "v1",
          kind: "DeleteOptions",
          propagationPolicy: "Foreground",
        },
      );
    },
  };
};
