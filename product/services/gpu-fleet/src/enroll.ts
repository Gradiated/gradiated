import {
  BOOTSTRAP_TAG,
  bootstrapPeer,
  enroll as runEnroll,
  enrollmentPayload,
  RunPodError,
  type BootstrapPeer,
  type EnrollmentResult,
  type InstanceTailnet,
  type RunPodClient,
  type RunSsh,
  type TailnetStatus,
} from "@gradiated/gpu-hosts";

import type { Bundle, GpuHost } from "./hosts.js";

export class ReimageNotSent extends Error {
  constructor(cause: unknown) {
    super(
      `RunPod did not re-image the pod: ${cause instanceof Error ? cause.message : String(cause)}`,
      { cause },
    );
  }
}

export type AuthKey = { key: string; id: string };
export type KeyClient = "bootstrap" | "inference";
// A minted key with its ID in the form rollout status stores: <client>:<id>.
export type MintedKey = { key: string; id: string };

export type EnrollmentDependencies = {
  runpod: RunPodClient;
  tailnet: { status: () => Promise<TailnetStatus>; run: RunSsh };
  instanceTailnet: (instanceId: string) => Promise<InstanceTailnet>;
  bootstrapKey: (podId: string) => Promise<AuthKey>;
  inferenceKey: (instanceId: string) => Promise<AuthKey>;
  // Each OAuth client can revoke only the keys it minted.
  revokeKey: (client: KeyClient, id: string) => Promise<void>;
  releaseName: (instanceId: string) => Promise<number>;
  claimName: (instanceId: string, since: Date) => Promise<string>;
  managementKey: (host: GpuHost) => Promise<string>;
  bundleUrl: (sha256: string) => Promise<string>;
  apiEndpoint: string;
};

const SKU_PRODUCTS: Record<string, string> = {
  B200: "NVIDIA B200",
  B300: "NVIDIA B300",
  H200: "NVIDIA H200",
  "RTX-PRO-6000": "NVIDIA RTX PRO 6000",
};

const sku = (host: GpuHost) => {
  const product = SKU_PRODUCTS[host.spec.inventory.gpuProduct];
  if (!product)
    throw new Error(
      `Unsupported GPU product ${host.spec.inventory.gpuProduct}`,
    );
  return `${host.spec.inventory.gpuCount}x ${product}`;
};

export const createEnrollment = (deps: EnrollmentDependencies) => ({
  pod: (host: GpuHost) => deps.runpod.pod(host.spec.provider.podId),

  tailnetOf: (host: GpuHost) => deps.instanceTailnet(host.spec.instanceId),

  peer: async (host: GpuHost): Promise<BootstrapPeer | null> =>
    bootstrapPeer(await deps.tailnet.status(), host.spec.provider.podId),

  bootstrapKey: async (host: GpuHost): Promise<MintedKey> => {
    const { key, id } = await deps.bootstrapKey(host.spec.provider.podId);
    return { key, id: `bootstrap:${id}` };
  },

  inferenceKey: async (host: GpuHost): Promise<MintedKey> => {
    const { key, id } = await deps.inferenceKey(host.spec.instanceId);
    return { key, id: `inference:${id}` };
  },

  // Any update resets the pod and wipes its container; a stopped pod must also
  // be started.
  // Throws ReimageNotSent when RunPod certainly did not apply the update. Any
  // other error leaves it unknown whether the pod is being re-imaged.
  reimage: async (host: GpuHost, image: string, bootstrapKey: string) => {
    const podId = host.spec.provider.podId;
    const current = await deps.runpod.pod(podId).catch((error: unknown) => {
      throw new ReimageNotSent(error);
    });
    try {
      await deps.runpod.update(podId, {
        imageName: image,
        ports: [],
        env: {
          // Tailscale settings come only from the operator: a carried-over
          // GRADIATED_TAILSCALE_LOGIN_SERVER could send the bootstrap key elsewhere.
          ...Object.fromEntries(
            Object.entries(current.env ?? {}).filter(
              ([name]) =>
                !name.startsWith("GRADIATED_TAILSCALE_") &&
                name !== "PUBLIC_KEY",
            ),
          ),
          GRADIATED_TAILSCALE_BOOTSTRAP_KEY: bootstrapKey,
        },
      });
    } catch (error) {
      // A 4xx answer (other than a timeout) is a refusal; anything else, such
      // as a 5xx or a lost connection, may have been applied.
      if (
        error instanceof RunPodError &&
        error.status >= 400 &&
        error.status < 500 &&
        error.status !== 408
      )
        throw new ReimageNotSent(error);
      throw error;
    }
    if (current.desiredStatus === "EXITED") await deps.runpod.start(podId);
  },

  enroll: async (
    host: GpuHost,
    peer: BootstrapPeer,
    bundle: Bundle,
    inferenceKey: string,
  ): Promise<EnrollmentResult> => {
    const instanceId = host.spec.instanceId;
    await deps.releaseName(instanceId);
    const payload = enrollmentPayload(
      { sku: sku(host) },
      {
        instance_id: instanceId,
        management_token: await deps.managementKey(host),
        auth_key: inferenceKey,
        api_endpoint: deps.apiEndpoint,
        host_bundle: {
          sha256: bundle.sha256,
          base_id: bundle.baseId,
          url: await deps.bundleUrl(bundle.sha256),
        },
      },
    );
    return runEnroll(
      deps.tailnet.run,
      { host: peer.ip, port: 22, hostKeySha256: peer.hostKeysSha256 },
      payload,
    );
  },

  // Done once the bootstrap address has left the netmap and the new
  // tag:gpu-inference device is named exactly gpu-<id>.
  promoted: async (
    host: GpuHost,
    bootstrapAddress: string,
    since: Date,
  ): Promise<{ address: string } | { waiting: string }> => {
    const status = await deps.tailnet.status();
    const stillBootstrap = Object.values(status.Peer ?? {}).some(
      (peer) =>
        peer.Online !== false &&
        (peer.TailscaleIPs ?? []).includes(bootstrapAddress) &&
        (peer.Tags ?? []).includes(BOOTSTRAP_TAG),
    );
    if (stillBootstrap)
      return { waiting: "The pod has not re-authenticated yet" };

    try {
      return { address: await deps.claimName(host.spec.instanceId, since) };
    } catch (error) {
      return { waiting: (error as Error).message };
    }
  },

  revoke: async (id: string) => {
    const [client, key] = id.split(":", 2) as [KeyClient, string];
    await deps.revokeKey(client, key);
  },
});

export type Enrollment = ReturnType<typeof createEnrollment>;
