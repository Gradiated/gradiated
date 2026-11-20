import type { InstanceService } from "@gradiated/control";
import { describe, expect, it, vi } from "vitest";
import { createRegistrations } from "../../src/instances/registration.js";
import type { InstanceProvider } from "../../src/instances/provider.js";
const id = "019d5a4a-0000-7000-8000-000000000001";
const instance = {
  provider: "runpod",
  providerAccountId: "account",
  providerInstanceId: "pod",
  region: "US-TX-1",
  faultDomain: "host",
  sku: "8x NVIDIA B300",
};
const payload = {
  version: 1 as const,
  instance_id: id,
  management_token: "private-management-key".repeat(3),
  auth_key: "tskey-auth-scoped",
  api_endpoint: "100.64.0.1",
  host_bundle: {
    sha256: "a".repeat(64),
    base_id: "ubuntu24-cuda13-amd64-v2",
    url: "https://artifacts.example/host.tar.gz",
  },
};
const setup = (stopped = false, ssh = true) => {
  const provider: InstanceProvider = {
    describe: async () => instance,
    isStopped: async () => stopped,
    supportsInPlace: async () => ssh,
    checkTailscaleEnrollment: async () => {
      if (!ssh) throw new Error("Pinned SSH required");
    },
    bootstrap: vi.fn(async () => ({
      tailscale_ip: "100.64.0.1",
      gpu_count: 8,
      gpu_product: "B300" as const,
      cpu: 96,
      memory_gib: 1280,
    })),
  };
  const revoke = vi.fn(async () => {});
  const audit = vi.fn();
  const registrations = createRegistrations({
    providers: { runpod: async () => provider },
    instances: async () =>
      ({
        register: async () => ({ ...instance, id }),
      }) as unknown as InstanceService,
    hostImage: "registry/gpu-base:pinned",
    managementKey: async () => ({
      key: "private-management-key".repeat(3),
      secretId: "management-secret",
    }),
    tailscaleAuthKey: async () => ({ key: "tskey-auth-scoped", revoke }),
    enrollmentPayload: async () => payload,
    audit,
  });
  return { provider, revoke, audit, registrations };
};
const request = {
  provider: "runpod",
  providerInstanceId: "pod",
  requestedBy: "operator@example.com",
  resetRunningPod: false,
};
const wait = async (s: ReturnType<typeof setup>, registrationId: string) => {
  await vi.waitFor(() =>
    expect(["prepared", "failed"]).toContain(
      s.registrations.get(registrationId)?.phase,
    ),
  );
  return s.registrations.get(registrationId)!;
};
describe("Kubernetes GPU enrollment", () => {
  it("prepares a running host without provider reset and returns credential-free Git inputs", async () => {
    const s = setup();
    const r = await s.registrations.start(request);
    const ready = await wait(s, r.id);
    expect(ready.phase).toBe("prepared");
    expect(ready.nodeName).toBe(`gpu-${id}`);
    expect(s.provider.bootstrap).toHaveBeenCalledWith(
      instance,
      "registry/gpu-base:pinned",
      payload,
      { allowReset: false },
    );
    expect(ready.kubernetes?.inventoryEntry).toMatchObject({
      instance_id: id,
      gpu_count: 8,
      cpu: 96,
      memory_gib: 1280,
    });
    expect(ready.kubernetes?.inventoryEntry.management_secret).toEqual({
      key: "management-secret",
    });
    expect(ready.kubernetes?.provider).toEqual({
      name: "runpod",
      accountId: "account",
      podId: "pod",
    });
    expect(JSON.stringify(ready)).not.toMatch(
      /private-management|private-encoded|tskey-auth/,
    );
    expect(JSON.stringify(s.audit.mock.calls)).not.toMatch(
      /private-management|private-encoded|tskey-auth/,
    );
    expect(s.revoke).toHaveBeenCalledOnce();
  });
  it("revokes the one-time key when bootstrap fails", async () => {
    const s = setup();
    vi.mocked(s.provider.bootstrap).mockRejectedValueOnce(
      new Error("GPU host refused active workloads"),
    );
    const r = await s.registrations.start(request);
    expect((await wait(s, r.id)).phase).toBe("failed");
    expect(s.revoke).toHaveBeenCalledOnce();
  });
  it("refuses an unpinned host before creating registration state or credentials", async () => {
    const s = setup(false, false);
    await expect(s.registrations.start(request)).rejects.toThrow("Pinned SSH");
    expect(s.registrations.list()).toEqual([]);
    expect(s.provider.bootstrap).not.toHaveBeenCalled();
  });
  it("requires explicit reset authorization when in-place enrollment is unavailable", async () => {
    const s = setup();
    s.provider.supportsInPlace = async () => false;
    await expect(s.registrations.start(request)).rejects.toThrow(
      "Enroll it in place over the tailnet",
    );
    expect(s.provider.bootstrap).not.toHaveBeenCalled();
  });
  it("passes an explicitly authorized reset through without changing the default", async () => {
    const s = setup();
    const r = await s.registrations.start({
      ...request,
      resetRunningPod: true,
    });
    await wait(s, r.id);
    expect(s.provider.bootstrap).toHaveBeenCalledWith(
      instance,
      expect.any(String),
      expect.any(Object),
      { allowReset: true },
    );
  });
  it("gives a provider its own GPU base image and every other provider the shared one", async () => {
    const providerFor = (name: string) => {
      const described = {
        ...instance,
        provider: name,
        ...(name === "aws" && {
          region: "us-east-1",
          faultDomain: "aws:us-east-1b",
        }),
      };
      const inPlace = vi.fn(async () => true);
      const provider: InstanceProvider = {
        describe: async () => described,
        isStopped: async () => false,
        supportsInPlace: inPlace,
        checkTailscaleEnrollment: async () => undefined,
        bootstrap: vi.fn(async () => ({
          tailscale_ip: "100.64.0.1",
          gpu_count: 1,
          gpu_product: "L4" as const,
          cpu: 3,
          memory_gib: 14,
        })),
      };
      return { provider, inPlace, described };
    };
    const runpod = providerFor("runpod");
    const aws = providerFor("aws");
    const registrations = createRegistrations({
      providers: {
        runpod: async () => runpod.provider,
        aws: async () => aws.provider,
      },
      instances: async () =>
        ({
          register: async () => ({ ...instance, id }),
        }) as unknown as InstanceService,
      hostImage: "registry/gpu-base:pinned",
      hostImages: { aws: "registry/gpu-base:aws" },
      managementKey: async () => ({
        key: "private-management-key".repeat(3),
        secretId: "management-secret",
      }),
      tailscaleAuthKey: async () => ({
        key: "tskey-auth-scoped",
        revoke: async () => {},
      }),
      enrollmentPayload: async () => payload,
      audit: () => {},
    });
    for (const [name, host, image] of [
      ["runpod", runpod, "registry/gpu-base:pinned"],
      ["aws", aws, "registry/gpu-base:aws"],
    ] as const) {
      const started = await registrations.start({ ...request, provider: name });
      await vi.waitFor(() =>
        expect(registrations.get(started.id)?.phase).toBe("prepared"),
      );
      expect(host.inPlace).toHaveBeenCalledWith("pod", image);
      expect(host.provider.bootstrap).toHaveBeenCalledWith(
        host.described,
        image,
        payload,
        { allowReset: false },
      );
    }
  });
  it("returns an EC2 host's account, region, zone and instance for its GpuHost", async () => {
    const described = {
      provider: "aws",
      providerAccountId: "111122223333",
      providerInstanceId: "i-0123456789abcdef0",
      region: "us-east-1",
      faultDomain: "aws:us-east-1b",
      sku: "1x NVIDIA L4",
    };
    const s = setup();
    const aws: InstanceProvider = {
      ...s.provider,
      describe: async () => described,
    };
    const registrations = createRegistrations({
      providers: { aws: async () => aws },
      instances: async () =>
        ({
          register: async () => ({ ...described, id }),
        }) as unknown as InstanceService,
      hostImage: "registry/gpu-base:pinned",
      managementKey: async () => ({
        key: "private-management-key".repeat(3),
        secretId: "management-secret",
      }),
      tailscaleAuthKey: async () => ({
        key: "tskey-auth-scoped",
        revoke: async () => {},
      }),
      enrollmentPayload: async () => payload,
      audit: () => {},
    });
    const started = await registrations.start({
      ...request,
      provider: "aws",
      providerInstanceId: "i-0123456789abcdef0",
    });
    await vi.waitFor(() =>
      expect(registrations.get(started.id)?.phase).toBe("prepared"),
    );
    expect(registrations.get(started.id)?.kubernetes?.provider).toEqual({
      name: "aws",
      accountId: "111122223333",
      region: "us-east-1",
      availabilityZone: "us-east-1b",
      ec2InstanceId: "i-0123456789abcdef0",
    });
  });
  it("refuses an EC2 host without a zone before touching it", async () => {
    const s = setup();
    const aws: InstanceProvider = {
      ...s.provider,
      describe: async () => ({ ...instance, provider: "aws" }),
    };
    const registrations = createRegistrations({
      providers: { aws: async () => aws },
      instances: async () => ({}) as unknown as InstanceService,
      hostImage: "registry/gpu-base:pinned",
      managementKey: async () => ({ key: "k", secretId: "s" }),
      tailscaleAuthKey: async () => ({ key: "k", revoke: async () => {} }),
      enrollmentPayload: async () => payload,
      audit: () => {},
    });
    await expect(
      registrations.start({ ...request, provider: "aws" }),
    ).rejects.toThrow("has no region or availability zone");
    expect(aws.bootstrap).not.toHaveBeenCalled();
  });
  it("rejects concurrent enrollment of the same provider host", async () => {
    const s = setup();
    vi.mocked(s.provider.bootstrap).mockImplementationOnce(
      () => new Promise(() => {}),
    );
    await s.registrations.start(request);
    await expect(s.registrations.start(request)).rejects.toThrow("still");
  });
});
