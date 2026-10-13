import { z } from "zod";

import {
  installInPlace,
  readEnrollment,
  verifyInPlaceBase,
} from "./in-place.js";
import type { RunSsh, SshTarget } from "./ssh.js";
import type { InstanceProvider, ProviderInstance } from "./provider.js";

const API = "https://rest.runpod.io/v1";
const REQUEST_TIMEOUT_MS = 30_000;

const podSchema = z.object({
  id: z.string(),
  consumerUserId: z.string(),
  machineId: z.string(),
  gpuCount: z.number().int().nonnegative(),
  vcpuCount: z.number().int().positive(),
  desiredStatus: z.string().optional(),
  imageName: z.string().optional(),
  publicIp: z.ipv4().nullish(),
  portMappings: z
    .record(z.string(), z.number().int().min(1).max(65535))
    .nullish(),
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
  readonly controlEndpoints?: () => Promise<Record<string, string>>;
  readonly inPlace?: {
    readonly run: RunSsh;
    readonly hostKeys: Readonly<Record<string, string>>;
  };
}

export const createRunPodProvider = ({
  apiKey,
  fetch: request = fetch,
  inPlace,
  controlEndpoints,
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
      throw new Error(`RunPod ${method} ${path} failed: ${response.status}`);
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

  const target = (current: z.infer<typeof podSchema>): SshTarget => {
    const hostKeySha256 = inPlace?.hostKeys[current.id];
    if (!inPlace || !hostKeySha256 || !/^[a-f0-9]{64}$/.test(hostKeySha256)) {
      throw new Error(
        `In-place enrollment needs a pinned SSH host key for ${current.id}`,
      );
    }
    const host = current.publicIp;
    const port = current.portMappings?.["22"];
    if (!host || !port || !current.ports?.includes("22/tcp")) {
      throw new Error(
        "In-place enrollment requires an existing direct SSH port; provider ports will not be changed",
      );
    }

    return { host, port, hostKeySha256 };
  };

  const enrollment = async (current: z.infer<typeof podSchema>) => {
    if (!inPlace?.hostKeys[current.id] || current.desiredStatus !== "RUNNING")
      return {};

    const result = await inPlace.run(target(current), readEnrollment);
    try {
      return z.record(z.string(), z.string()).parse(JSON.parse(result));
    } catch {
      throw new Error("The in-place enrollment identity is invalid");
    }
  };

  return {
    async checkTailscaleEnrollment(podId) {
      const current = await pod(podId);
      if (!inPlace?.hostKeys[podId] || !current.ports?.includes("22/tcp"))
        throw new Error(
          "GPU registration requires a pinned SSH connection for Tailscale enrollment",
        );
    },
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

    async environment(podId, options) {
      const current = await pod(podId);

      return {
        ...(current.env ?? {}),
        ...(!options?.providerOnly && (await enrollment(current))),
      };
    },

    async supportsInPlace(podId, image) {
      if (!inPlace?.hostKeys[podId]) return false;

      const current = await pod(podId);
      if (current.desiredStatus !== "RUNNING") {
        throw new Error(
          "In-place enrollment requires a running pod; no provider changes were made",
        );
      }
      const sshTarget = target(current);
      if (!(await enrollment(current)).GRADIATED_INSTANCE_ID) {
        await verifyInPlaceBase(inPlace.run, sshTarget, image);
      }

      return true;
    },

    async isStopped(podId) {
      return (await pod(podId)).desiredStatus === "EXITED";
    },

    async bootstrap(instance, image, environment, options) {
      const current = await pod(instance.providerInstanceId);
      if (
        !options?.allowReset &&
        current.desiredStatus !== "EXITED" &&
        (await this.supportsInPlace?.(current.id, image))
      ) {
        return installInPlace(inPlace!.run, target(current), environment);
      }
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
      });
      // Updating a stopped pod only changes its configuration; it stays stopped.
      if (current.desiredStatus === "EXITED") {
        await call("POST", `/pods/${current.id}/start`);
      }
      const deadline = Date.now() + 30 * 60 * 1000;
      while (Date.now() < deadline) {
        const ready = await pod(current.id);
        if (
          ready.desiredStatus === "RUNNING" &&
          ready.publicIp &&
          ready.portMappings?.["22"]
        ) {
          try {
            return await installInPlace(
              inPlace!.run,
              target(ready),
              environment,
            );
          } catch {
            /* The image can still be preparing the host agent. */
          }
        }
        await new Promise((resolve) => setTimeout(resolve, 10000));
      }
      throw new Error(
        "GPU bootstrap did not become ready; provider capacity was left intact",
      );
    },
  };
};
