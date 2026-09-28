import { z } from "zod";

import type {
  HostImage,
  InstanceProvider,
  ProviderInstance,
} from "./provider.js";

const API = "https://rest.runpod.io/v1";
const REGISTRY_AUTH_PREFIX = "gradiated-host-";
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

const registryAuthSchema = z.object({ id: z.string(), name: z.string() });

export interface RunPodOptions {
  readonly apiKey: string;
  readonly fetch?: typeof fetch;
  readonly now?: () => Date;
}

export const createRunPodProvider = ({
  apiKey,
  fetch: request = fetch,
  now = () => new Date(),
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

  const registryAuth = async (
    podId: string,
    registry: NonNullable<HostImage["registry"]>,
  ) => {
    const prefix = `${REGISTRY_AUTH_PREFIX}${podId}-`;
    const created = registryAuthSchema.parse(
      await call("POST", "/containerregistryauth", {
        name: `${prefix}${now().getTime()}`,
        username: registry.username,
        password: registry.password,
      }),
    );
    const replaced = async () => {
      const existing = z
        .array(registryAuthSchema)
        .parse((await call("GET", "/containerregistryauth")) ?? []);
      for (const auth of existing) {
        if (auth.name.startsWith(prefix) && auth.id !== created.id) {
          await call("DELETE", `/containerregistryauth/${auth.id}`);
        }
      }
    };

    return { id: created.id, removeReplaced: replaced };
  };

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

      const auth = image.registry
        ? await registryAuth(current.id, image.registry)
        : null;

      // Any PATCH resets the pod and wipes its container filesystem.
      await call("PATCH", `/pods/${current.id}`, {
        imageName: image.reference,
        env: { ...current.env, ...environment },
        ports: [...new Set([...(current.ports ?? []), SERVING_PORT])],
        ...(auth ? { containerRegistryAuthId: auth.id } : {}),
      });
      await auth?.removeReplaced();
    },
  };
};
