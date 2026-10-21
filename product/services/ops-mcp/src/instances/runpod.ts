import { z } from "zod";

import {
  installInPlace,
  readEnrollment,
  verifyInPlaceBase,
} from "./in-place.js";
import type { RunSsh, SshTarget } from "./ssh.js";
import type { InstanceProvider, ProviderInstance } from "./provider.js";
import {
  bootstrapPeer,
  waitForPromotion,
  type TailnetStatus,
} from "./tailnet.js";

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
  readonly tailnet: {
    readonly run: RunSsh;
    readonly status: () => Promise<TailnetStatus>;
    readonly promotionTimeoutMs?: number;
    readonly promotionPollMs?: number;
    readonly promotedAddress?: (
      instanceId: string,
      since: Date,
    ) => Promise<string>;
  };
}

export const createRunPodProvider = ({
  apiKey,
  fetch: request = fetch,
  tailnet,
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

  const tailnetTarget = async (podId: string): Promise<SshTarget | null> => {
    const peer = bootstrapPeer(await tailnet.status(), podId);
    return (
      peer && { host: peer.ip, port: 22, hostKeySha256: peer.hostKeysSha256 }
    );
  };

  const transport = async (current: z.infer<typeof podSchema>) => {
    const target = await tailnetTarget(current.id);
    return target && { run: tailnet.run, target };
  };

  const install = async (
    current: z.infer<typeof podSchema>,
    environment: Readonly<Record<string, string>>,
  ) => {
    const route = await transport(current);
    if (!route) throw new Error("No enrollment connection to the GPU pod");

    const started = new Date();
    const { promotion, ...inventory } = await installInPlace(
      route.run,
      route.target,
      environment,
    );
    if (!promotion) return inventory;

    await waitForPromotion(
      tailnet.status,
      route.target.host,
      tailnet.promotionTimeoutMs,
      tailnet.promotionPollMs,
    );
    if (!tailnet.promotedAddress)
      throw new Error("Promoted GPU address lookup is not configured");
    const { instance_id } = z
      .object({ instance_id: z.uuid() })
      .parse(
        JSON.parse(
          Buffer.from(
            environment.GRADIATED_GPU_BOOTSTRAP ?? "",
            "base64",
          ).toString(),
        ),
      );
    // The bootstrap device can go offline a few seconds before the
    // re-authenticated device appears in the device list.
    const deadline = Date.now() + (tailnet.promotionTimeoutMs ?? 180_000);
    for (;;) {
      try {
        return {
          ...inventory,
          tailscaleIp: await tailnet.promotedAddress(instance_id, started),
        };
      } catch (error) {
        if (Date.now() >= deadline) throw error;
      }
      await new Promise((resolve) =>
        setTimeout(resolve, tailnet.promotionPollMs ?? 5_000),
      );
    }
  };

  const enrollment = async (current: z.infer<typeof podSchema>) => {
    if (current.desiredStatus !== "RUNNING") return {};

    const route = await transport(current);
    if (!route) return {};

    const result = await route.run(route.target, readEnrollment);
    try {
      return z.record(z.string(), z.string()).parse(JSON.parse(result));
    } catch {
      throw new Error("The in-place enrollment identity is invalid");
    }
  };

  return {
    async checkTailscaleEnrollment(podId) {
      if (await tailnetTarget(podId)) return;

      // A stopped v5 pod joins the tailnet only after registration starts it.
      const current = await pod(podId);
      if (
        current.desiredStatus !== "EXITED" ||
        !current.env?.GRADIATED_TAILSCALE_BOOTSTRAP_KEY
      )
        throw new Error(
          `GPU registration requires gpu-bootstrap-${podId} online in the tailnet ` +
            "(v5 GPU base image with a bootstrap key), or a stopped v5 pod",
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
      const current = await pod(podId);
      const route = await transport(current);
      if (!route) return false;

      if (current.desiredStatus !== "RUNNING") {
        throw new Error(
          "In-place enrollment requires a running pod; no provider changes were made",
        );
      }
      if (!(await enrollment(current)).GRADIATED_INSTANCE_ID) {
        if (current.imageName !== image)
          throw new Error(
            "Unenrolled GPU pod does not use the approved base image",
          );

        await verifyInPlaceBase(route.run, route.target, image);
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
        return install(current, environment);
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
        env: Object.fromEntries(
          Object.entries(current.env ?? {}).filter(
            ([name]) => name !== "GRADIATED_GPU_BOOTSTRAP",
          ),
        ),
      });
      // Updating a stopped pod only changes its configuration; it stays stopped.
      if (current.desiredStatus === "EXITED") {
        await call("POST", `/pods/${current.id}/start`);
      }
      const deadline = Date.now() + 30 * 60 * 1000;
      while (Date.now() < deadline) {
        const ready = await pod(current.id);
        if (ready.desiredStatus === "RUNNING") {
          try {
            return await install(ready, environment);
          } catch {
            /* The pod can still be joining the tailnet or preparing the host agent. */
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
