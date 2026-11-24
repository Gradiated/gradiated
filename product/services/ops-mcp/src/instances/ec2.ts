import { randomUUID } from "node:crypto";

import {
  managedInstance,
  prepareReplacement,
  removeBootstrapAccess,
  replacementProgress,
  replaceWithTemplateImage,
  type AwsGpuClient,
  type Ec2Instance,
  type EnrollmentPayload,
} from "@gradiated/gpu-hosts";

import type {
  GpuInventory,
  InstanceProvider,
  ProviderInstance,
} from "./provider.js";
import { tailnetEnrollment, type TailnetAccess } from "./tailnet.js";

export interface AwsOptions {
  readonly client: AwsGpuClient;
  // Mints the single-use tag:gpu-bootstrap key the instance joins the tailnet
  // with; it reaches the host only through its bootstrap secret.
  readonly bootstrapKey?: (
    instanceId: string,
  ) => Promise<{ key: string; revoke: () => Promise<void> }>;
  readonly audit?: (event: Record<string, unknown>) => void;
  readonly tailnet: TailnetAccess;
  readonly pollMs?: number;
  // How long a fresh instance waiting for its bootstrap secret gets to join.
  readonly freshJoinTimeoutMs?: number;
  // How long a re-imaged instance gets to boot, join and enroll.
  readonly reimageTimeoutMs?: number;
}

const MINUTE = 60_000;

// AWS GPU hosts are EC2 instances in the GPU account, running the GPU base
// image under a host launcher from the launch template. The launcher waits on
// a fresh root volume for the instance's bootstrap secret, then starts the
// container, which joins the tailnet as gpu-bootstrap-<instance ID>. From
// there enrollment is the same as on RunPod. Once enrolled, the secret is
// deleted and the instance profile removed, so the host holds no AWS
// credentials. A re-image replaces the root volume with the AMI the launch
// template's default version pins: the instance, its ID and its capacity
// stay. The single-use key is written only once the new root volume is in
// place, so an old root's launcher can never consume it. Nothing here stops or
// terminates an instance.
export const createAwsProvider = ({
  client,
  bootstrapKey,
  audit,
  tailnet,
  pollMs = 10_000,
  freshJoinTimeoutMs = 10 * MINUTE,
  reimageTimeoutMs = 30 * MINUTE,
}: AwsOptions): InstanceProvider => {
  const enrollment = tailnetEnrollment(tailnet, audit);
  const sleep = () => new Promise((resolve) => setTimeout(resolve, pollMs));

  const managed = (instanceId: string) => managedInstance(client, instanceId);

  // The host enrolled: it keeps no way to read AWS. A failure here fails the
  // registration, so the host is not committed while it still has credentials.
  const removeCredentials = async (
    instanceId: string,
    inventory: GpuInventory,
  ) => {
    const { left, kept } = await removeBootstrapAccess(client, instanceId);
    if (kept.length) {
      audit?.({
        event: "aws_instance_profile_left",
        provider_instance_id: instanceId,
        kept,
      });
      throw new Error(
        `EC2 instance ${instanceId} enrolled, but it has instance profile ${kept.join(", ")}, not the bootstrap profile; remove it before committing its GpuHost`,
      );
    }
    if (left.length) {
      audit?.({
        event: "aws_bootstrap_credentials_left",
        provider_instance_id: instanceId,
        left,
      });
      throw new Error(
        `EC2 instance ${instanceId} enrolled, but ${left.join(" and ")} could not be removed; remove them before committing its GpuHost`,
      );
    }
    audit?.({
      event: "aws_bootstrap_credentials_removed",
      provider_instance_id: instanceId,
    });
    return inventory;
  };

  // Each instance gets its own single-use key, minted as it is delivered in
  // its bootstrap secret; both are gone once enrollment ends either way.
  const withBootstrapKey = async <T>(
    instanceId: string,
    image: string,
    work: (deliver: () => Promise<void>) => Promise<T>,
  ): Promise<T> => {
    const mint = bootstrapKey;
    if (!mint) throw new Error("GPU bootstrap key minting is not configured");
    let joining: Awaited<ReturnType<typeof mint>> | undefined;
    try {
      return await work(async () => {
        await replacementsSettled(instanceId);
        joining ??= await mint(instanceId);
        await client.writeBootstrapSecret(instanceId, {
          image,
          tailscaleAuthKey: joining.key,
        });
      });
    } finally {
      // An unused key stays valid until it expires, so a failed revocation
      // is recorded for cleanup.
      await joining?.revoke().catch(() =>
        audit?.({
          event: "tailscale_bootstrap_key_revocation_failed",
          provider_instance_id: instanceId,
        }),
      );
      await client.deleteBootstrapSecret(instanceId).catch(() =>
        audit?.({
          event: "aws_bootstrap_secret_deletion_failed",
          provider_instance_id: instanceId,
        }),
      );
    }
  };

  // Waits for gpu-bootstrap-<id> and enrolls it; the host can still be
  // booting, pulling the image or preparing the host agent.
  const enrollWhenJoined = async (
    instanceId: string,
    payload: EnrollmentPayload,
    timeoutMs: number,
    late: string,
  ) => {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const { state } = await client.instance(instanceId);
      if (state === "shutting-down" || state === "terminated")
        throw new Error(`GPU bootstrap failed: the instance is ${state}`);
      if (state === "running" && (await enrollment.target(instanceId))) {
        try {
          return await enrollment.install(instanceId, payload);
        } catch {
          /* The host can still be preparing the host agent. */
        }
      }
      await sleep();
    }
    throw new Error(late);
  };

  const waitFor = async (
    what: string,
    timeoutMs: number,
    check: () => Promise<boolean>,
  ) => {
    const deadline = Date.now() + timeoutMs;
    while (!(await check())) {
      if (Date.now() >= deadline)
        throw new Error(`Timed out waiting for ${what}`);
      await sleep();
    }
  };

  const running = (instanceId: string, what: string, timeoutMs: number) =>
    waitFor(what, timeoutMs, async () => {
      const { state } = await client.instance(instanceId);
      if (state === "shutting-down" || state === "terminated")
        throw new Error(`EC2 instance ${instanceId} is ${state}`);
      return state === "running";
    });

  // Run before any key is written. A replace-root-volume task left in flight
  // (ops-mcp exited or a poll failed after starting it) still swaps the root
  // volume: a secret written now could reach the old root's launcher, which
  // consumes the single-use key just before it is wiped. So the key waits
  // until every task has ended and the instance runs again on its new root;
  // a host whose last replacement failed gets nothing.
  const replacementsSettled = async (instanceId: string) => {
    let { inFlight, last } = await replacementProgress(client, instanceId);
    const waited = inFlight.length > 0;
    if (waited) {
      audit?.({
        event: "aws_root_volume_replacement_in_flight",
        provider_instance_id: instanceId,
        task_ids: inFlight.map((task) => task.id),
      });
      await waitFor(
        `replace-root-volume task ${inFlight.map((task) => task.id).join(", ")} of ${instanceId} to end`,
        reimageTimeoutMs,
        async () => {
          ({ inFlight, last } = await replacementProgress(client, instanceId));
          return !inFlight.length;
        },
      );
    }
    if (last?.state.startsWith("fail"))
      throw new Error(
        `Replacing the root volume of ${instanceId} ${last.state} (task ${last.id}), ` +
          "so no bootstrap key was written; re-image it only when that reset is explicitly authorized",
      );
    if (waited)
      await running(
        instanceId,
        `EC2 instance ${instanceId} to run on its new root volume`,
        10 * MINUTE,
      );
  };

  // The order matters: the profile and the key reach only the new root
  // volume. A stopped instance's old root can still hold a launcher waiting
  // for its secret, and anything on a running one could copy the profile's
  // credentials, so neither is there until that root is gone.
  const reimage = async (
    current: Ec2Instance,
    deliver: () => Promise<void>,
  ) => {
    const { id: instanceId, state } = current;
    if (await prepareReplacement(client, current))
      audit?.({
        event: "aws_bootstrap_profile_removed",
        provider_instance_id: instanceId,
      });
    // Replacing a root volume needs a running instance.
    if (state === "stopped") {
      await client.start(instanceId);
      await running(
        instanceId,
        `EC2 instance ${instanceId} to start`,
        10 * MINUTE,
      );
    }
    const { imageId, task } = await replaceWithTemplateImage(
      client,
      instanceId,
      randomUUID(),
    );
    audit?.({
      event: "aws_root_volume_replacement_started",
      provider_instance_id: instanceId,
      task_id: task.id,
      image_id: imageId,
    });
    await waitFor(
      `replace-root-volume task ${task.id}`,
      reimageTimeoutMs,
      async () => {
        const { state: taskState } = await client.replaceRootVolumeTask(
          instanceId,
          task.id,
        );
        if (taskState.startsWith("fail"))
          throw new Error(
            `Replacing the root volume of ${instanceId} ${taskState}`,
          );
        return taskState === "succeeded";
      },
    );
    await running(
      instanceId,
      `EC2 instance ${instanceId} to run on its new root volume`,
      10 * MINUTE,
    );
    if (await client.associateBootstrapProfile(instanceId))
      audit?.({
        event: "aws_bootstrap_profile_associated",
        provider_instance_id: instanceId,
      });
    await deliver();
  };

  const refusal = (instanceId: string, reason: string) =>
    new Error(
      `GPU registration requires gpu-bootstrap-${instanceId} online in the tailnet, ` +
        `a stopped instance, or an authorized reset: ${reason}`,
    );

  const NOT_FRESH =
    "the instance no longer has its bootstrap instance profile, so it is not a fresh instance waiting for its secret";

  // A running instance with no bootstrap peer is fresh, its launcher waiting
  // for the secret, only while it still has the bootstrap profile its launch
  // template gave it; enrollment removes that profile.
  const freshProfile = (instanceId: string) =>
    client.bootstrapProfileAssociated(instanceId);

  // A host already promoted to gpu-<id> started its container: its one-shot
  // launcher will not read another secret.
  const neverPromoted = async (instanceId: string, uuid: string) => {
    if (!tailnet.hasDevice)
      throw new Error("GPU tailnet device lookup is not configured");
    if (await tailnet.hasDevice(uuid))
      throw refusal(
        instanceId,
        `gpu-${uuid} already exists in the tailnet, so its launcher already ran`,
      );
  };

  return {
    async describe(instanceId) {
      const found = await managed(instanceId);
      const gpus = await client.gpus(found.instanceType);
      return {
        provider: "aws",
        providerAccountId: found.accountId,
        providerInstanceId: found.id,
        region: client.region,
        faultDomain: `aws:${found.availabilityZone}`,
        sku: `${gpus.count}x ${gpus.name}`,
      } satisfies ProviderInstance;
    },

    async checkTailscaleEnrollment(instanceId, options) {
      if (await enrollment.target(instanceId)) return;

      // A running instance may be a fresh one whose launcher waits for its
      // bootstrap secret. Only an authorized reset re-images a running
      // instance that is not, and a stopped one is re-imaged as it starts.
      const { state } = await client.instance(instanceId);
      if ((state !== "running" && state !== "stopped") || !bootstrapKey)
        throw refusal(
          instanceId,
          bootstrapKey
            ? `the instance is ${state}`
            : "bootstrap key minting is not configured",
        );
      if (
        state === "running" &&
        options?.allowReset !== true &&
        !(await freshProfile(instanceId))
      )
        throw refusal(instanceId, NOT_FRESH);
    },

    async isStopped(instanceId) {
      return (await client.instance(instanceId)).state === "stopped";
    },

    // The container image is not visible through EC2: it is the image named
    // in the bootstrap secret ops-mcp writes, and enrollment checks the host
    // bundle against the image's base ID.
    async supportsInPlace(instanceId) {
      const { state } = await client.instance(instanceId);
      if (await enrollment.target(instanceId)) {
        if (state !== "running")
          throw new Error(
            "In-place enrollment requires a running instance; no provider changes were made",
          );
        return true;
      }
      return state === "running" && (await freshProfile(instanceId));
    },

    async bootstrap(instance, image, payload, options) {
      const instanceId = instance.providerInstanceId;
      const current = await managed(instanceId);
      const reset = options?.allowReset === true || current.state === "stopped";

      if (!reset) {
        if (current.state !== "running")
          throw new Error(
            `Refusing to change EC2 instance ${instanceId} while it is ${current.state}`,
          );
        if (await enrollment.target(instanceId))
          return removeCredentials(
            instanceId,
            await enrollment.install(instanceId, payload),
          );
        // A fresh instance waits for its key; nothing else on it changes.
        // Any other instance would never read the secret, and the wait could
        // only time out.
        if (!(await freshProfile(instanceId)))
          throw refusal(instanceId, NOT_FRESH);
        await neverPromoted(instanceId, payload.instance_id);
        return withBootstrapKey(instanceId, image, async (deliver) => {
          await deliver();
          return removeCredentials(
            instanceId,
            await enrollWhenJoined(
              instanceId,
              payload,
              freshJoinTimeoutMs,
              `gpu-bootstrap-${instanceId} did not join the tailnet after its bootstrap secret was written, ` +
                "and the instance was not changed. Its launcher runs only on a fresh root volume; " +
                "re-image it only when that reset is explicitly authorized.",
            ),
          );
        });
      }

      if (current.state !== "running" && current.state !== "stopped")
        throw new Error(
          `Refusing to re-image EC2 instance ${instanceId} while it is ${current.state}`,
        );
      return withBootstrapKey(instanceId, image, async (deliver) => {
        await reimage(current, deliver);
        return removeCredentials(
          instanceId,
          await enrollWhenJoined(
            instanceId,
            payload,
            reimageTimeoutMs,
            "GPU bootstrap did not become ready; the instance and its capacity were left intact",
          ),
        );
      });
    },
  };
};
