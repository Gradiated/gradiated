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
const setup = (stopped = false, ssh = true) => {
  const provider: InstanceProvider = {
    describe: async () => instance,
    environment: async () => ({}),
    isStopped: async () => stopped,
    supportsInPlace: async () => ssh,
    checkTailscaleEnrollment: async () => {
      if (!ssh) throw new Error("Pinned SSH required");
    },
    bootstrap: vi.fn(async () => ({
      tailscaleIp: "100.64.0.1",
      gpuCount: 8,
      gpuProduct: "B300",
      cpu: 96,
      memoryGiB: 1280,
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
    bootstrap: async () => ({
      GRADIATED_GPU_BOOTSTRAP: "private-encoded-bootstrap",
    }),
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
      { GRADIATED_GPU_BOOTSTRAP: "private-encoded-bootstrap" },
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
  it("rejects concurrent enrollment of the same provider host", async () => {
    const s = setup();
    vi.mocked(s.provider.bootstrap).mockImplementationOnce(
      () => new Promise(() => {}),
    );
    await s.registrations.start(request);
    await expect(s.registrations.start(request)).rejects.toThrow("still");
  });
});
