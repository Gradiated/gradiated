import { z } from "zod";

import type { InstanceProvider, ProviderInstance } from "./provider.js";

const API = "https://rest.runpod.io/v1";
const REQUEST_TIMEOUT_MS = 30_000;
// The host proxy's port; RunPod only reaches ports declared on the pod.
const SERVING_PORT = "8888/http";

const podSchema = z.object({
  id: z.string(),
  consumerUserId: z.string(),
  machineId: z.string(),
  gpuCount: z.number().int().nonnegative(),
  vcpuCount: z.number().int().positive(),
  desiredStatus: z.string().optional(),
  ports: z.array(z.string()).nullish(),
  env: z.record(z.string(), z.string()).nullish(),
  machine: z.object({
    dataCenterId: z.string().nullish(),
    gpuTypeId: z.string().nullish(),
  }),
});

export interface RunPodOptions {
  readonly apiKey: string;
  readonly fetch?: typeof fetch;
}

export const createRunPodProvider = ({
  apiKey,
  fetch: request = fetch,
}: RunPodOptions): InstanceProvider => {
  const call = async (
    method: string,
    path: string,
    body?: unknown,
  ): Promise<unknown> => {
    const response = await request(`${API}${path}`, {
      method,
      headers: {
        authorization: `Bearer ${apiKey}`,
        "content-type": "application/json",
        // RunPod's edge rejects requests without a client identity.
        "user-agent": "gradiated-ops-mcp",
      },
      body: body === undefined ? null : JSON.stringify(body),
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
    const text = await response.text();
    if (!response.ok) {
      throw new Error(
        `RunPod ${method} ${path} failed: ${response.status} ${text}`,
      );
    }

    return text === "" ? null : JSON.parse(text);
  };

  const pod = async (podId: string) =>
    podSchema.parse(
      await call(
        "GET",
        `/pods/${encodeURIComponent(podId)}?includeMachine=true`,
      ),
    );

  return {
    async describe(podId) {
      const found = await pod(podId);
      const sku =
        found.gpuCount > 0
          ? `${found.gpuCount}x ${found.machine.gpuTypeId ?? "unknown GPU"}`
          : `cpu-${found.vcpuCount}vcpu`;

      return {
        provider: "runpod",
        providerAccountId: found.consumerUserId,
        providerInstanceId: found.id,
        region: found.machine.dataCenterId ?? null,
        faultDomain: `runpod:${found.machineId}`,
        sku,
      } satisfies ProviderInstance;
    },

    async environment(podId) {
      return (await pod(podId)).env ?? {};
    },

    async isStopped(podId) {
      return (await pod(podId)).desiredStatus === "EXITED";
    },

    async bootstrap(instance, image, environment, options) {
      const current = await pod(instance.providerInstanceId);
      if (current.desiredStatus !== "EXITED" && !options?.allowReset) {
        throw new Error(
          "Refusing to reset a RunPod pod that is running or has unknown status: " +
            "an image or environment update can stop it and release scarce GPU capacity. " +
            "Reset it only when that is explicitly authorized.",
        );
      }

      // Any PATCH resets the pod and wipes its container filesystem. The image
      // pulls through the account's ECR delegation, so no registry login is set.
      await call("PATCH", `/pods/${current.id}`, {
        imageName: image,
        env: { ...current.env, ...environment },
        ports: [...new Set([...(current.ports ?? []), SERVING_PORT])],
      });
    },
  };
};
