import { describe, expect, it, vi } from "vitest";
import { ENROLL_COMMAND, type RunSsh } from "@gradiated/gpu-hosts";

import { createAwsProvider } from "../../src/instances/ec2.js";
import { createRegistrations } from "../../src/instances/registration.js";
import { fakeEc2, INSTANCE } from "../support/aws.js";

const image =
  "873716897517.dkr.ecr.us-east-1.amazonaws.com/gradiated/prod/inference:gpu-base-inputs-" +
  "c".repeat(64);
const payload = {
  version: 1 as const,
  instance_id: "00000000-0000-4000-8000-000000000001",
  management_token: "private_management_" + "x".repeat(24),
  auth_key: "tskey-auth-inference",
  api_endpoint: "100.64.0.1",
  host_bundle: {
    sha256: "a".repeat(64),
    base_id: "ubuntu24-cuda13-amd64-v3",
    url: "https://artifacts.example/host.tar.gz?X-Amz-Signature=private",
  },
};
const inventory = {
  tailscale_ip: "100.64.0.9",
  gpu_count: 1,
  gpu_product: "L4",
  cpu: 3,
  memory_gib: 12,
};
const enrolled = JSON.stringify({ version: 1, ...inventory, promotion: false });

const setup = (
  ec2: ReturnType<typeof fakeEc2> = fakeEc2(),
  // UUIDs that already have a gpu-<id> device in the tailnet.
  promoted: string[] = [],
) => {
  const run = vi.fn<RunSsh>(async () => enrolled);
  const revoke = vi.fn(async () => undefined);
  const bootstrapKey = vi.fn(async () => ({
    key: "tskey-auth-bootstrap-1",
    revoke,
  }));
  const audit = vi.fn();
  const provider = createAwsProvider({
    client: ec2.client,
    bootstrapKey,
    audit,
    tailnet: {
      run,
      status: ec2.status,
      releaseName: async () => 0,
      claimName: async () => "100.64.0.9",
      hasDevice: async (uuid) => promoted.includes(uuid),
    },
    pollMs: 1,
    freshJoinTimeoutMs: 200,
    reimageTimeoutMs: 1_000,
  });
  return { ...ec2, run, revoke, bootstrapKey, audit, provider };
};

const changes = (calls: string[]) =>
  calls
    .filter(
      (call) =>
        !call.startsWith("instance ") &&
        !call.startsWith("gpus ") &&
        !call.startsWith("bootstrapProfileAssociated ") &&
        !call.startsWith("replaceRootVolumeTask ") &&
        !call.startsWith("replaceRootVolumeTasks "),
    )
    .map((call) => call.split(" ")[0]);

describe("EC2 GPU hosts", () => {
  it("describes an instance by its account, region, zone and GPUs", async () => {
    const { provider } = setup();
    expect(await provider.describe(INSTANCE)).toEqual({
      provider: "aws",
      providerAccountId: "111122223333",
      providerInstanceId: INSTANCE,
      region: "us-east-1",
      faultDomain: "aws:us-east-1b",
      sku: "1x L4",
    });
  });

  it("refuses an instance the GPU fleet does not manage", async () => {
    const { provider, host } = setup(fakeEc2({ tags: {} }));
    await expect(provider.describe(INSTANCE)).rejects.toThrow(
      "is not tagged gradiated:managed=gpu-fleet",
    );
    await expect(
      provider.bootstrap(
        {
          provider: "aws",
          providerAccountId: "111122223333",
          providerInstanceId: INSTANCE,
          region: "us-east-1",
          faultDomain: "aws:us-east-1b",
          sku: "1x L4",
        },
        image,
        payload,
        { allowReset: true },
      ),
    ).rejects.toThrow("is not tagged");
    expect(changes(host.calls)).toEqual([]);
  });

  it("enrolls a host already online as gpu-bootstrap-<id> in place, then removes its AWS access", async () => {
    const ec2 = fakeEc2({ launched: true });
    ec2.host.joined = true;
    const s = setup(ec2);
    const instance = await s.provider.describe(INSTANCE);
    expect(await s.provider.supportsInPlace!(INSTANCE, image)).toBe(true);

    await expect(
      s.provider.bootstrap(instance, image, payload),
    ).resolves.toEqual(inventory);
    expect(s.run).toHaveBeenCalledWith(
      { host: "100.64.0.9", port: 22, hostKeySha256: [expect.any(String)] },
      ENROLL_COMMAND,
      JSON.stringify(payload),
      30 * 60 * 1000,
    );
    // No key, no secret write, no re-image: only the cleanup.
    expect(s.bootstrapKey).not.toHaveBeenCalled();
    expect(changes(s.host.calls)).toEqual([
      "deleteBootstrapSecret",
      "disassociateInstanceProfile",
    ]);
    expect(s.host.profile).toBe(false);
  });

  it("gives a fresh instance its key through its bootstrap secret without resetting it", async () => {
    const s = setup();
    const instance = await s.provider.describe(INSTANCE);
    await s.provider.checkTailscaleEnrollment(INSTANCE);
    expect(await s.provider.isStopped(INSTANCE)).toBe(false);
    expect(await s.provider.supportsInPlace!(INSTANCE, image)).toBe(true);

    await expect(
      s.provider.bootstrap(instance, image, payload),
    ).resolves.toEqual(inventory);
    expect(s.bootstrapKey).toHaveBeenCalledWith(INSTANCE);
    expect(s.host.secrets).toEqual([
      { image, tailscaleAuthKey: "tskey-auth-bootstrap-1" },
    ]);
    expect(changes(s.host.calls)).toEqual([
      "writeBootstrapSecret",
      "deleteBootstrapSecret",
      "disassociateInstanceProfile",
      "deleteBootstrapSecret",
    ]);
    expect(s.revoke).toHaveBeenCalledOnce();
    expect(s.host.secret).toBeUndefined();
    expect(s.host.profile).toBe(false);
    // With no replacement on record, the key goes out after one look.
    expect(
      s.host.calls.filter((call) => call.startsWith("replaceRootVolumeTasks ")),
    ).toEqual([`replaceRootVolumeTasks ${INSTANCE}`]);
    expect(s.host.consumed).toEqual([
      { root: 0, key: "tskey-auth-bootstrap-1" },
    ]);
  });

  it("waits out a root replacement an earlier attempt left in flight before writing the key", async () => {
    // ops-mcp exited after starting the replacement: the instance still runs
    // on its old root, with the bootstrap profile attached and its launcher
    // waiting for a secret.
    const ec2 = fakeEc2();
    await ec2.client.replaceRootVolume(
      INSTANCE,
      "earlier",
      ec2.host.templateImage,
    );
    ec2.host.calls.length = 0;
    const s = setup(ec2);

    await expect(
      s.provider.bootstrap(await s.provider.describe(INSTANCE), image, payload),
    ).resolves.toEqual(inventory);
    // The key was written once, after the task ended, and only the new root
    // read it.
    expect(s.host.replacements.map((task) => task.state)).toEqual([
      "succeeded",
    ]);
    const settled = s.host.calls.lastIndexOf(
      `replaceRootVolumeTasks ${INSTANCE}`,
    );
    expect(
      s.host.calls.indexOf(`writeBootstrapSecret ${INSTANCE}`),
    ).toBeGreaterThan(settled);
    expect(s.host.secrets).toEqual([
      { image, tailscaleAuthKey: "tskey-auth-bootstrap-1" },
    ]);
    expect(s.host.consumed).toEqual([
      { root: 1, key: "tskey-auth-bootstrap-1" },
    ]);
    expect(s.bootstrapKey).toHaveBeenCalledOnce();
    expect(s.host.tasks).toBe(1);
    expect(s.audit).toHaveBeenCalledWith(
      expect.objectContaining({
        event: "aws_root_volume_replacement_in_flight",
        task_ids: ["replacevol-1"],
      }),
    );
  });

  it("writes no key when a root replacement an earlier attempt left in flight fails", async () => {
    const ec2 = fakeEc2();
    ec2.host.replacements.push({
      id: "replacevol-9",
      state: "pending",
      imageId: ec2.host.templateImage,
      ends: "failed",
    });
    const s = setup(ec2);

    await expect(
      s.provider.bootstrap(await s.provider.describe(INSTANCE), image, payload),
    ).rejects.toThrow(
      `Replacing the root volume of ${INSTANCE} failed (task replacevol-9)`,
    );
    expect(s.host.replacements[0]!.state).toBe("failed");
    expect(s.host.secrets).toEqual([]);
    expect(s.host.consumed).toEqual([]);
    expect(s.bootstrapKey).not.toHaveBeenCalled();
    expect(changes(s.host.calls)).toEqual(["deleteBootstrapSecret"]);
  });

  it("never resets a running instance whose launcher already ran without authorization", async () => {
    const s = setup(fakeEc2({ launched: true }));
    const instance = await s.provider.describe(INSTANCE);

    await expect(
      s.provider.bootstrap(instance, image, payload),
    ).rejects.toThrow("the instance was not changed");
    expect(changes(s.host.calls)).toEqual([
      "writeBootstrapSecret",
      "deleteBootstrapSecret",
    ]);
    expect(s.host.tasks).toBe(0);
    expect(s.revoke).toHaveBeenCalledOnce();
    expect(s.host.secret).toBeUndefined();
    // Its profile stays until a host enrolls.
    expect(s.host.profile).toBe(true);
  });

  it("re-images an authorized running instance by replacing its root volume, in the contract's order", async () => {
    const s = setup(fakeEc2({ launched: true, profile: false }));
    const instance = await s.provider.describe(INSTANCE);

    await expect(
      s.provider.bootstrap(instance, image, payload, { allowReset: true }),
    ).resolves.toEqual(inventory);
    expect(changes(s.host.calls)).toEqual([
      "associateBootstrapProfile",
      "launchTemplateImage",
      "replaceRootVolume",
      "writeBootstrapSecret",
      "deleteBootstrapSecret",
      "disassociateInstanceProfile",
      "deleteBootstrapSecret",
    ]);
    expect(s.host.tasks).toBe(1);
    // Onto the AMI the launch template's default version pins, not the
    // instance's original launch AMI.
    expect(s.host.calls).toContain(
      `replaceRootVolume ${INSTANCE} ami-0fedcba9876543210`,
    );
    expect(s.host.instance.imageId).toBe("ami-0fedcba9876543210");
    // The secret is written only after the task succeeded on the new root.
    const succeeded = s.host.calls.lastIndexOf(
      `replaceRootVolumeTask ${INSTANCE} replacevol-1`,
    );
    expect(
      s.host.calls.indexOf(`writeBootstrapSecret ${INSTANCE}`),
    ).toBeGreaterThan(succeeded);
    expect(s.host.secrets).toEqual([
      { image, tailscaleAuthKey: "tskey-auth-bootstrap-1" },
    ]);
    expect(s.host.consumed).toEqual([
      { root: 1, key: "tskey-auth-bootstrap-1" },
    ]);
    expect(s.host.profile).toBe(false);
    expect(s.revoke).toHaveBeenCalledOnce();
    expect(s.audit).toHaveBeenCalledWith(
      expect.objectContaining({ event: "aws_root_volume_replacement_started" }),
    );
  });

  it.each([true, false])(
    "starts a stopped instance and replaces its root volume before writing its key (launcher ran: %s)",
    async (launched) => {
      // An old root that never got its secret still has a launcher waiting.
      const s = setup(fakeEc2({ state: "stopped", launched }));
      const instance = await s.provider.describe(INSTANCE);
      expect(await s.provider.isStopped(INSTANCE)).toBe(true);
      await s.provider.checkTailscaleEnrollment(INSTANCE);

      await expect(
        s.provider.bootstrap(instance, image, payload),
      ).resolves.toEqual(inventory);
      expect(changes(s.host.calls)).toEqual([
        "associateBootstrapProfile",
        "start",
        "launchTemplateImage",
        "replaceRootVolume",
        "writeBootstrapSecret",
        "deleteBootstrapSecret",
        "disassociateInstanceProfile",
        "deleteBootstrapSecret",
      ]);
      // Only the new root volume ever read the single-use key.
      expect(s.host.consumed).toEqual([
        { root: 1, key: "tskey-auth-bootstrap-1" },
      ]);
    },
  );

  it("writes no key when the root volume replacement fails", async () => {
    const ec2 = fakeEc2({ state: "stopped" });
    ec2.client.replaceRootVolumeTask = async (_id, task) => ({
      id: task,
      state: "failed",
    });
    const s = setup(ec2);
    await expect(
      s.provider.bootstrap(await s.provider.describe(INSTANCE), image, payload),
    ).rejects.toThrow("failed");
    expect(s.host.secrets).toEqual([]);
    expect(s.bootstrapKey).not.toHaveBeenCalled();
  });

  it.each(["running", "stopped"])(
    "refuses to reset a %s instance with another instance profile before replacing its root",
    async (state) => {
      const ec2 = fakeEc2({ state, launched: true, profile: false });
      ec2.client.associateBootstrapProfile = async (id) => {
        ec2.host.calls.push(`associateBootstrapProfile ${id}`);
        throw new Error(
          `EC2 instance ${id} has instance profile arn:aws:iam::111122223333:instance-profile/other, not gradiated-gpu-prod-host-bootstrap`,
        );
      };
      const s = setup(ec2);
      await expect(
        s.provider.bootstrap(
          await s.provider.describe(INSTANCE),
          image,
          payload,
          { allowReset: true },
        ),
      ).rejects.toThrow("instance-profile/other");
      expect(changes(s.host.calls)).toEqual([
        "associateBootstrapProfile",
        "deleteBootstrapSecret",
      ]);
      expect(s.host.tasks).toBe(0);
      expect(s.host.root).toBe(0);
      expect(s.bootstrapKey).not.toHaveBeenCalled();
    },
  );

  it("refuses a running instance that lost its bootstrap profile instead of waiting on a launcher that will not run", async () => {
    // As after enrollment removed the profile and ops-mcp restarted.
    const s = setup(fakeEc2({ launched: true, profile: false }));
    await expect(s.provider.checkTailscaleEnrollment(INSTANCE)).rejects.toThrow(
      `requires gpu-bootstrap-${INSTANCE} online in the tailnet, a stopped instance, or an authorized reset`,
    );
    expect(await s.provider.supportsInPlace!(INSTANCE, image)).toBe(false);
    await expect(
      s.provider.bootstrap(await s.provider.describe(INSTANCE), image, payload),
    ).rejects.toThrow("no longer has its bootstrap instance profile");
    // An authorized reset still may re-image it.
    await expect(
      s.provider.checkTailscaleEnrollment(INSTANCE, { allowReset: true }),
    ).resolves.toBeUndefined();
    expect(changes(s.host.calls)).toEqual([]);
    expect(s.bootstrapKey).not.toHaveBeenCalled();
  });

  it("refuses a running instance already promoted to gpu-<UUID> instead of writing a secret it will never read", async () => {
    // Promoted, but ops-mcp restarted before its credentials were removed.
    const s = setup(fakeEc2({ launched: true }), [payload.instance_id]);
    await expect(
      s.provider.bootstrap(await s.provider.describe(INSTANCE), image, payload),
    ).rejects.toThrow(
      `requires gpu-bootstrap-${INSTANCE} online in the tailnet, a stopped instance, or an authorized reset: ` +
        `gpu-${payload.instance_id} already exists`,
    );
    expect(changes(s.host.calls)).toEqual([]);
    expect(s.host.secrets).toEqual([]);
    expect(s.bootstrapKey).not.toHaveBeenCalled();
  });

  it.each(["pending", "stopping", "shutting-down", "terminated"])(
    "changes nothing on a %s instance",
    async (state) => {
      const s = setup(fakeEc2({ state }));
      const instance = await s.provider.describe(INSTANCE);
      await expect(
        s.provider.checkTailscaleEnrollment(INSTANCE),
      ).rejects.toThrow(`gpu-bootstrap-${INSTANCE} online`);
      for (const allowReset of [false, true])
        await expect(
          s.provider.bootstrap(instance, image, payload, { allowReset }),
        ).rejects.toThrow("Refusing");
      expect(changes(s.host.calls)).toEqual([]);
      expect(s.bootstrapKey).not.toHaveBeenCalled();
    },
  );

  it("fails an enrollment whose AWS access could not be removed", async () => {
    const ec2 = fakeEc2({ launched: true });
    ec2.host.joined = true;
    ec2.client.disassociateInstanceProfile = async () => {
      throw new Error("AccessDenied");
    };
    const s = setup(ec2);
    await expect(
      s.provider.bootstrap(await s.provider.describe(INSTANCE), image, payload),
    ).rejects.toThrow("its instance profile could not be removed");
    expect(s.audit).toHaveBeenCalledWith(
      expect.objectContaining({ event: "aws_bootstrap_credentials_left" }),
    );
  });

  it("registers a fresh instance through the shared registration flow", async () => {
    const s = setup();
    const register = vi.fn(async () => ({
      id: payload.instance_id,
      provider: "aws",
      providerAccountId: "111122223333",
      providerInstanceId: INSTANCE,
      region: "us-east-1",
      faultDomain: "aws:us-east-1b",
      sku: "1x L4",
      createdAt: new Date(),
      updatedAt: new Date(),
      retiredAt: null,
    }));
    const registrations = createRegistrations({
      providers: { aws: async () => s.provider },
      instances: async () => ({ register, retire: vi.fn() }),
      hostImage: image,
      enrollmentPayload: async () => payload,
      managementKey: async () => ({
        key: payload.management_token,
        secretId: `gradiated/prod/platform/gpu-host/${payload.instance_id}`,
      }),
      tailscaleAuthKey: async () => ({
        key: "tskey-auth-inference",
        revoke: async () => undefined,
      }),
      audit: () => undefined,
    });
    const started = await registrations.start({
      provider: "aws",
      providerInstanceId: INSTANCE,
      resetRunningPod: false,
      requestedBy: "tester@gradiated.com",
    });
    await vi.waitFor(() =>
      expect(registrations.get(started.id)?.phase).toBe("prepared"),
    );
    expect(register).toHaveBeenCalledWith(
      expect.objectContaining({
        provider: "aws",
        faultDomain: "aws:us-east-1b",
      }),
    );
    expect(
      registrations.get(started.id)?.kubernetes?.inventoryEntry,
    ).toMatchObject({ gpu_product: "L4", gpu_count: 1 });
    expect(s.host.tasks).toBe(0);
  });
});
