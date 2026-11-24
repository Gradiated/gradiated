import { createHash } from "node:crypto";

import {
  BOOTSTRAP_TAG,
  bootstrapPeer,
  ec2Refusal,
  enroll as runEnroll,
  enrollmentPayload,
  managedInstance,
  prepareReplacement,
  removeBootstrapAccess,
  replacementProgress,
  replaceWithTemplateImage,
  RunPodError,
  type AwsGpuClient,
  type BootstrapPeer,
  type EnrollmentResult,
  type InstanceTailnet,
  type RunPodClient,
  type RunSsh,
  type TailnetStatus,
} from "@gradiated/gpu-hosts";

import {
  ec2InstanceOf,
  isAws,
  providerInstanceId,
  runPodId,
  type Bundle,
  type GpuHost,
} from "./hosts.js";

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
  // The operator role client of each AWS GPU account the fleet may change.
  aws?: (accountId: string) => AwsGpuClient | undefined;
  tailnet: { status: () => Promise<TailnetStatus>; run: RunSsh };
  instanceTailnet: (instanceId: string) => Promise<InstanceTailnet>;
  bootstrapKey: (providerInstanceId: string) => Promise<AuthKey>;
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
  H100: "NVIDIA H100",
  H200: "NVIDIA H200",
  L4: "NVIDIA L4",
  L40S: "NVIDIA L40S",
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

// A host's EC2 client, only for the account and region its GpuHost names.
const ec2 = (deps: EnrollmentDependencies, host: GpuHost) => {
  if (!isAws(host)) throw new Error(`${host.metadata.name} is not an AWS host`);
  const { accountId, region } = host.spec.provider;
  const client = deps.aws?.(accountId);
  if (!client || client.accountId !== accountId)
    throw new Error(`AWS access to account ${accountId} is not configured`);
  if (client.region !== region)
    throw new Error(
      `AWS access to account ${accountId} is for ${client.region}, not ${region}`,
    );
  return { client, id: ec2InstanceOf(host), accountId };
};

// One task per re-image request: EC2 treats a repeated token as the same task.
const replaceToken = (host: GpuHost, requestedAt: string) =>
  createHash("sha256")
    .update(`${host.metadata.uid}/${requestedAt}`)
    .digest("hex");

const onNewRoot = async (
  client: AwsGpuClient,
  id: string,
  accountId: string,
  taskId: string,
) => {
  const instance = await managedInstance(client, id, accountId);
  const { inFlight, last } = await replacementProgress(client, id);
  if (inFlight.length || last?.id !== taskId || last.state !== "succeeded")
    throw new Error(
      `Replace-root-volume task ${taskId} of ${id} is not the last to have succeeded`,
    );
  if (instance.state !== "running")
    throw new Error(`EC2 instance ${id} is ${instance.state}, not running`);
};

export const createEnrollment = (deps: EnrollmentDependencies) => ({
  pod: (host: GpuHost) => deps.runpod.pod(runPodId(host)),

  instance: async (host: GpuHost) => {
    const { client, id } = ec2(deps, host);
    return client.instance(id);
  },

  instanceStorage: async (host: GpuHost, instanceType: string) =>
    ec2(deps, host).client.instanceStorage(instanceType),

  // Why the instance must not be re-imaged: untagged, in another account, or
  // with an instance profile other than the bootstrap profile.
  ec2Refusal: async (host: GpuHost) => {
    const { client, id, accountId } = ec2(deps, host);
    const instance = await client.instance(id);
    const refusal = ec2Refusal(instance, accountId);
    if (refusal) return refusal;
    if (
      instance.instanceProfileArn &&
      !(await client.bootstrapProfileAssociated(id, { includeDetaching: true }))
    )
      return `EC2 instance ${id} has instance profile ${instance.instanceProfileArn}, not the bootstrap profile; the operator leaves it alone`;
  },

  // The old root boots again, so its bootstrap access goes first.
  startInstance: async (host: GpuHost) => {
    const { client, id, accountId } = ec2(deps, host);
    await prepareReplacement(
      client,
      await managedInstance(client, id, accountId),
    );
    await client.start(id);
  },

  replacements: async (host: GpuHost) => {
    const { client, id } = ec2(deps, host);
    return replacementProgress(client, id);
  },

  // Sent again with the same request time, it returns the same task.
  replaceRoot: async (host: GpuHost, requestedAt: string) => {
    const { client, id, accountId } = ec2(deps, host);
    await prepareReplacement(
      client,
      await managedInstance(client, id, accountId),
    );
    return replaceWithTemplateImage(
      client,
      id,
      replaceToken(host, requestedAt),
    );
  },

  rootVolumeTask: async (host: GpuHost, taskId: string) => {
    const { client, id } = ec2(deps, host);
    return client.replaceRootVolumeTask(id, taskId);
  },

  // The profile and the key reach only the new root volume: both wait until
  // this rollout's replacement is the last, every task has ended, and the
  // instance runs again.
  attachBootstrapProfile: async (host: GpuHost, taskId: string) => {
    const { client, id, accountId } = ec2(deps, host);
    await onNewRoot(client, id, accountId, taskId);
    await client.associateBootstrapProfile(id);
  },

  deliverBootstrapKey: async (
    host: GpuHost,
    taskId: string,
    image: string,
    key: string,
  ) => {
    const { client, id, accountId } = ec2(deps, host);
    await onNewRoot(client, id, accountId, taskId);
    if (!(await client.bootstrapProfileAssociated(id)))
      throw new Error(
        `EC2 instance ${id} has no bootstrap instance profile, so no bootstrap key was written`,
      );

    await client.writeBootstrapSecret(id, { image, tailscaleAuthKey: key });
  },

  removeBootstrapAccess: async (host: GpuHost) => {
    const { client, id } = ec2(deps, host);
    return removeBootstrapAccess(client, id);
  },

  tailnetOf: (host: GpuHost) => deps.instanceTailnet(host.spec.instanceId),

  peer: async (host: GpuHost): Promise<BootstrapPeer | null> =>
    bootstrapPeer(await deps.tailnet.status(), providerInstanceId(host)),

  bootstrapKey: async (host: GpuHost): Promise<MintedKey> => {
    const { key, id } = await deps.bootstrapKey(providerInstanceId(host));
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
    const podId = runPodId(host);
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
