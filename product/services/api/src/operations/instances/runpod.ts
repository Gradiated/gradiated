import { z } from "@hono/zod-openapi";

import type {
  HostImage,
  InstanceProvider,
  ProviderInstance,
} from "./provider.js";

const API = "https://rest.runpod.io/v1";
const REGISTRY_AUTH_PREFIX = "gradiated-host-";
const REQUEST_TIMEOUT_MS = 30_000;

const podSchema = z.object({
  id: z.string(),
  consumerUserId: z.string(),
  machineId: z.string(),
  gpuCount: z.number().int().nonnegative(),
  vcpuCount: z.number().int().positive(),
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
        "user-agent": "gradiated-instance-register",
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

    async bootstrap(instance, image, environment) {
      const current = await pod(instance.providerInstanceId);
      const auth = image.registry
        ? await registryAuth(current.id, image.registry)
        : null;

      // Any PATCH resets the pod and wipes its container filesystem.
      await call("PATCH", `/pods/${current.id}`, {
        imageName: image.reference,
        env: { ...current.env, ...environment },
        ...(auth ? { containerRegistryAuthId: auth.id } : {}),
      });
      await auth?.removeReplaced();
    },
  };
};
