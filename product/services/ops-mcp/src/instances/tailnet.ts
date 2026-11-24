import {
  bootstrapPeer,
  enroll,
  waitForPromotion,
  type EnrollmentPayload,
  type RunSsh,
  type SshTarget,
  type TailnetStatus,
} from "@gradiated/gpu-hosts";

import type { GpuInventory } from "./provider.js";

export type TailnetAccess = {
  readonly run: RunSsh;
  readonly status: () => Promise<TailnetStatus>;
  readonly promotionTimeoutMs?: number;
  readonly promotionPollMs?: number;
  // Removes the offline devices an earlier boot left under gpu-<id>.
  readonly releaseName?: (instanceId: string) => Promise<number>;
  // Finds the promoted device, makes sure it is named gpu-<id> and returns
  // its address.
  readonly claimName?: (instanceId: string, since: Date) => Promise<string>;
  // Whether a tag:gpu-inference device, online or not, already uses
  // gpu-<id>: the host enrolled and promoted before.
  readonly hasDevice?: (instanceId: string) => Promise<boolean>;
};

// Enrollment over Tailscale SSH to a host online as
// gpu-bootstrap-<provider instance ID>, the same for every provider.
export const tailnetEnrollment = (
  tailnet: TailnetAccess,
  audit?: (event: Record<string, unknown>) => void,
) => {
  const target = async (
    providerInstanceId: string,
  ): Promise<SshTarget | null> => {
    const peer = bootstrapPeer(await tailnet.status(), providerInstanceId);
    return (
      peer && { host: peer.ip, port: 22, hostKeySha256: peer.hostKeysSha256 }
    );
  };

  const install = async (
    providerInstanceId: string,
    payload: EnrollmentPayload,
  ): Promise<GpuInventory> => {
    const found = await target(providerInstanceId);
    if (!found) throw new Error("No enrollment connection to the GPU host");

    if (!tailnet.releaseName || !tailnet.claimName)
      throw new Error("GPU tailnet name management is not configured");
    const instanceId = payload.instance_id;
    const released = await tailnet.releaseName(instanceId);
    if (released)
      audit?.({
        event: "tailscale_stale_devices_removed",
        instance_id: instanceId,
        count: released,
      });

    const started = new Date();
    const {
      version: _version,
      promotion,
      ...inventory
    } = await enroll(tailnet.run, found, payload);
    if (!promotion) return inventory;

    await waitForPromotion(
      tailnet.status,
      found.host,
      tailnet.promotionTimeoutMs,
      tailnet.promotionPollMs,
    );
    // The bootstrap device can go offline a few seconds before the
    // re-authenticated device appears in the device list.
    const deadline = Date.now() + (tailnet.promotionTimeoutMs ?? 180_000);
    for (;;) {
      try {
        return {
          ...inventory,
          tailscale_ip: await tailnet.claimName(instanceId, started),
        };
      } catch (error) {
        if (Date.now() >= deadline) throw error;
      }
      await new Promise((resolve) =>
        setTimeout(resolve, tailnet.promotionPollMs ?? 5_000),
      );
    }
  };

  return { target, install };
};
