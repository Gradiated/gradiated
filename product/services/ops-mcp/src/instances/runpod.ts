import {
  createRunPodClient,
  type EnrollmentPayload,
  type RunPod,
} from "@gradiated/gpu-hosts";

import type { InstanceProvider, ProviderInstance } from "./provider.js";
import { tailnetEnrollment, type TailnetAccess } from "./tailnet.js";

export interface RunPodOptions {
  readonly apiKey: string;
  readonly fetch?: typeof fetch;
  // Mints the single-use tag:gpu-bootstrap key a reset or stopped pod joins
  // the tailnet with.
  readonly bootstrapKey?: (
    podId: string,
  ) => Promise<{ key: string; revoke: () => Promise<void> }>;
  readonly audit?: (event: Record<string, unknown>) => void;
  readonly tailnet: TailnetAccess;
}

export const createRunPodProvider = ({
  apiKey,
  fetch: request = fetch,
  bootstrapKey,
  audit,
  tailnet,
}: RunPodOptions): InstanceProvider => {
  const runpod = createRunPodClient({
    apiKey,
    fetch: request,
    userAgent: "gradiated-ops-mcp",
  });
  const pod = runpod.pod;
  const enrollment = tailnetEnrollment(tailnet, audit);
  const tailnetTarget = enrollment.target;

  const transport = async (current: RunPod) => {
    const target = await tailnetTarget(current.id);
    return target && { run: tailnet.run, target };
  };

  const install = (current: RunPod, payload: EnrollmentPayload) =>
    enrollment.install(current.id, payload);

  return {
    async checkTailscaleEnrollment(podId, options) {
      if (await tailnetTarget(podId)) return;

      // A stopped or reset pod joins the tailnet only after registration
      // re-images it with a bootstrap key.
      const current = await pod(podId);
      const resettable =
        current.desiredStatus === "EXITED" || options?.allowReset === true;
      if (
        !resettable ||
        (!bootstrapKey && !current.env?.GRADIATED_TAILSCALE_BOOTSTRAP_KEY)
      )
        throw new Error(
          `GPU registration requires gpu-bootstrap-${podId} online in the tailnet ` +
            "(v5 GPU base image with a bootstrap key), a stopped pod, or an authorized reset",
        );
    },
    async describe(podId) {
      const [found, identity] = await Promise.all([
        pod(podId),
        runpod.identity(podId),
      ]);
      const sku =
        found.gpuCount > 0
          ? `${found.gpuCount}x ${found.machine.gpuTypeId ?? "unknown GPU"}`
          : `cpu-${found.vcpuCount}vcpu`;

      return {
        provider: "runpod",
        providerAccountId: identity.consumerUserId,
        providerInstanceId: found.id,
        region: found.machine.dataCenterId ?? null,
        faultDomain: `runpod:${identity.machineId}`,
        sku,
      } satisfies ProviderInstance;
    },

    // A pod online as gpu-bootstrap-<pod> must run the approved image, which provides
    // gradiated-host; enrollment then checks the bundle against the image's base ID.
    async supportsInPlace(podId, image) {
      const current = await pod(podId);
      const route = await transport(current);
      if (!route) return false;

      if (current.desiredStatus !== "RUNNING") {
        throw new Error(
          "In-place enrollment requires a running pod; no provider changes were made",
        );
      }
      if (current.imageName !== image)
        throw new Error(
          "Unenrolled GPU pod does not use the approved base image",
        );
      return true;
    },

    async isStopped(podId) {
      return (await pod(podId)).desiredStatus === "EXITED";
    },

    async bootstrap(instance, image, payload, options) {
      const current = await pod(instance.providerInstanceId);
      if (
        !options?.allowReset &&
        current.desiredStatus !== "EXITED" &&
        (await this.supportsInPlace?.(current.id, image))
      ) {
        return install(current, payload);
      }
      if (current.desiredStatus !== "EXITED" && !options?.allowReset) {
        throw new Error(
          "Refusing to reset a RunPod pod that is running or has unknown status: " +
            "an image or environment update can stop it and release scarce GPU capacity. " +
            "Reset it only when that is explicitly authorized.",
        );
      }

      // Each pod gets its own single-use key, revoked once enrollment ends.
      const joining = bootstrapKey && (await bootstrapKey(current.id));
      try {
        // Any PATCH resets the pod and wipes its container filesystem. The
        // image pulls through the account's ECR delegation, so no registry
        // login is set. v5 pods expose no ports: Tailscale SSH is the only
        // shell, so the public SSH key is dropped too.
        await runpod.update(current.id, {
          imageName: image,
          ports: [],
          env: {
            ...Object.fromEntries(
              Object.entries(current.env ?? {}).filter(
                ([name]) =>
                  name !== "GRADIATED_GPU_BOOTSTRAP" && name !== "PUBLIC_KEY",
              ),
            ),
            ...(joining && { GRADIATED_TAILSCALE_BOOTSTRAP_KEY: joining.key }),
          },
        });
        // Updating a stopped pod only changes its configuration; it stays stopped.
        if (current.desiredStatus === "EXITED") {
          await runpod.start(current.id);
        }
        const deadline = Date.now() + 30 * 60 * 1000;
        while (Date.now() < deadline) {
          const ready = await pod(current.id);
          if (
            ready.desiredStatus === "ERROR" ||
            ready.desiredStatus === "TERMINATED"
          )
            throw new Error(
              `GPU bootstrap failed: pod is ${ready.desiredStatus}`,
            );

          if (ready.desiredStatus === "RUNNING") {
            try {
              return await install(ready, payload);
            } catch {
              /* The pod can still be joining the tailnet or preparing the host agent. */
            }
          }
          await new Promise((resolve) => setTimeout(resolve, 10000));
        }
        throw new Error(
          "GPU bootstrap did not become ready; provider capacity was left intact",
        );
      } finally {
        // An unused key stays valid until it expires, so a failed revocation
        // is recorded for cleanup.
        await joining?.revoke().catch(() =>
          audit?.({
            event: "tailscale_bootstrap_key_revocation_failed",
            provider_instance_id: current.id,
          }),
        );
      }
    },
  };
};
