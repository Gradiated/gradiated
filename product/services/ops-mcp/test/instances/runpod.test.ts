import { describe, expect, it, vi } from "vitest";
import { createRunPodProvider } from "../../src/instances/runpod.js";
import { ENROLL_COMMAND, type RunSsh } from "@gradiated/gpu-hosts";
import { fakeRunPod, rtxPod } from "../support/runpod.js";
const image = "registry.example/gpu-base:pinned";
const inventory = {
  tailscale_ip: "100.64.0.1",
  gpu_count: 2,
  gpu_product: "RTX-PRO-6000",
  cpu: 28,
  memory_gib: 112,
};
const payload = {
  version: 1 as const,
  instance_id: "00000000-0000-4000-8000-000000000001",
  management_token: "private_management_" + "x".repeat(24),
  auth_key: "tskey-auth-inference",
  api_endpoint: "100.64.0.1",
  host_bundle: {
    sha256: "a".repeat(64),
    base_id: "ubuntu24-cuda13-amd64-v2",
    url: "https://artifacts.example/host.tar.gz?X-Amz-Signature=private",
  },
};
// What gradiated-host enroll prints for the inventory above.
const enrolled = (promotion: boolean, address = "100.64.0.1") =>
  JSON.stringify({
    version: 1,
    tailscale_ip: address,
    gpu_count: 2,
    gpu_product: "RTX-PRO-6000",
    cpu: 28,
    memory_gib: 112,
    promotion,
  });
const running = {
  ...rtxPod,
  desiredStatus: "RUNNING",
  imageName: image,
};
const setup = (pod = running) => {
  const runpod = fakeRunPod(pod);
  const run = vi.fn<RunSsh>(async () => enrolled(false));
  const provider = createRunPodProvider({
    apiKey: "private-api-key",
    fetch: runpod.fetch,
    tailnet: { run, status: async () => bootstrapStatus() },
  });
  return { runpod, run, provider };
};
describe("RunPod Kubernetes enrollment", () => {
  it.each(["RUNNING", "CREATED", "UNKNOWN"])(
    "refuses %s provider reset without explicit authorization",
    async (status) => {
      const s = fakeRunPod({ ...running, desiredStatus: status });
      const provider = createRunPodProvider({
        apiKey: "key",
        fetch: s.fetch,
        tailnet: { run: vi.fn<RunSsh>(), status: async () => ({ Peer: {} }) },
      });
      await expect(
        provider.bootstrap(await provider.describe("pod1"), image, payload),
      ).rejects.toThrow("Refusing to reset");
      expect(s.calls.every((c) => c.method === "GET")).toBe(true);
    },
  );
  it("re-images and starts a stopped pod with its own bootstrap key and no public SSH", async () => {
    const s = setup();
    let started = false;
    const fetch = vi.fn(
      async (input: string | URL | Request, init?: RequestInit) => {
        const method = init?.method ?? "GET";
        if (method === "POST") started = true;
        return new Response(
          JSON.stringify(
            method === "GET"
              ? { ...running, desiredStatus: started ? "RUNNING" : "EXITED" }
              : {},
          ),
        );
      },
    );
    const revoke = vi.fn(async () => {});
    const bootstrapKey = vi.fn(async () => ({
      key: "tskey-auth-bootstrap",
      revoke,
    }));
    const provider = createRunPodProvider({
      apiKey: "key",
      fetch,
      bootstrapKey,
      tailnet: {
        run: s.run,
        status: async () => bootstrapStatus(),
        releaseName: async () => 0,
        claimName: async () => "100.64.1.2",
      },
    });
    await provider.bootstrap(await provider.describe("pod1"), image, payload);
    const patch = fetch.mock.calls.find(
      ([, init]) => init?.method === "PATCH",
    )![1]!;
    expect(bootstrapKey).toHaveBeenCalledWith("pod1");
    expect(JSON.parse(String(patch.body))).toEqual({
      imageName: image,
      ports: [],
      env: { GRADIATED_TAILSCALE_BOOTSTRAP_KEY: "tskey-auth-bootstrap" },
    });
    expect(
      fetch.mock.calls.some(([url]) => String(url).endsWith("/start")),
    ).toBe(true);
    expect(revoke).toHaveBeenCalledOnce();
  });

  it("revokes the bootstrap key when the reset fails, and records a failed revocation", async () => {
    const s = setup();
    const revoke = vi.fn(async () => {
      throw new Error("Tailscale key revocation returned 500");
    });
    const audit = vi.fn();
    const provider = createRunPodProvider({
      apiKey: "key",
      fetch: (async (input, init) =>
        init?.method === "PATCH"
          ? new Response("", { status: 500 })
          : s.runpod.fetch(input, init)) as typeof globalThis.fetch,
      bootstrapKey: async () => ({ key: "tskey-auth-bootstrap", revoke }),
      audit,
      tailnet: { run: s.run, status: async () => ({ Peer: {} }) },
    });
    await expect(
      provider.bootstrap(await provider.describe("pod1"), image, payload, {
        allowReset: true,
      }),
    ).rejects.toThrow("RunPod PATCH /pods/pod1 failed: 500");
    expect(revoke).toHaveBeenCalledOnce();
    expect(audit).toHaveBeenCalledWith({
      event: "tailscale_bootstrap_key_revocation_failed",
      provider_instance_id: "pod1",
    });
  });
  it("redacts provider failure bodies that could echo bootstrap credentials", async () => {
    const s = setup();
    const fetch = (async (input, init) =>
      init?.method === "PATCH"
        ? new Response("private-bootstrap-material", { status: 500 })
        : s.runpod.fetch(input, init)) as typeof globalThis.fetch;
    const provider = createRunPodProvider({
      apiKey: "key",
      fetch,
      tailnet: { run: s.run, status: async () => bootstrapStatus() },
    });
    await expect(
      provider.bootstrap(await provider.describe("pod1"), image, payload, {
        allowReset: true,
      }),
    ).rejects.toThrow("RunPod PATCH /pods/pod1 failed: 500");
    await expect(
      provider.bootstrap(await provider.describe("pod1"), image, payload, {
        allowReset: true,
      }),
    ).rejects.not.toThrow("private-bootstrap-material");
  });
});

const bootstrapStatus = (hostName = "gpu-bootstrap-pod1") => ({
  Peer: {
    node: {
      HostName: hostName,
      TailscaleIPs: ["100.64.0.9", "fd7a::9"],
      Tags: ["tag:gpu-bootstrap"],
      Online: true,
      sshHostKeys: ["ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHN5bnRoZXRpYw=="],
    },
  },
});

describe("RunPod tailnet enrollment", () => {
  const v5 = running;
  const tailnetSetup = (statuses: unknown[]) => {
    const runpod = fakeRunPod(v5);
    const status = vi.fn(
      async () =>
        (statuses.length > 1 ? statuses.shift() : statuses[0]) as never,
    );
    const run = vi.fn<RunSsh>(async () => enrolled(true, "100.64.0.9"));
    const releaseName = vi.fn(async () => 1);
    const claimName = vi.fn(async () => "100.64.1.2");
    const provider = createRunPodProvider({
      apiKey: "private-api-key",
      fetch: runpod.fetch,
      tailnet: {
        run,
        status,
        releaseName,
        claimName,
        promotionTimeoutMs: 300,
        promotionPollMs: 10,
      },
    });
    return { runpod, run, status, releaseName, claimName, provider };
  };

  it("enrolls a bootstrap pod over Tailscale SSH without public SSH or provider changes", async () => {
    const s = tailnetSetup([
      bootstrapStatus(),
      bootstrapStatus(),
      bootstrapStatus(),
      bootstrapStatus(),
      bootstrapStatus(),
      { Peer: {} },
    ]);
    await expect(
      s.provider.checkTailscaleEnrollment("pod1"),
    ).resolves.toBeUndefined();
    const instanceId = payload.instance_id;
    await expect(
      s.provider.bootstrap(await s.provider.describe("pod1"), image, payload),
    ).resolves.toEqual({ ...inventory, tailscale_ip: "100.64.1.2" });
    expect(s.releaseName).toHaveBeenCalledWith(instanceId);
    expect(s.releaseName.mock.invocationCallOrder[0]).toBeLessThan(
      s.run.mock.invocationCallOrder.at(-1)!,
    );
    expect(s.claimName).toHaveBeenCalledWith(instanceId, expect.any(Date));
    expect(s.runpod.calls.every((c) => c.method === "GET")).toBe(true);
    const [target, command, input] = s.run.mock.calls.at(-1)!;
    expect(target.host).toBe("100.64.0.9");
    expect(target.port).toBe(22);
    expect([target.hostKeySha256].flat()).toHaveLength(1);
    expect(command).toBe(ENROLL_COMMAND);
    expect(JSON.parse(input!)).toEqual(payload);
  });

  it("keeps looking up the promoted address until the new device is listed", async () => {
    const s = tailnetSetup([
      bootstrapStatus(),
      bootstrapStatus(),
      bootstrapStatus(),
      bootstrapStatus(),
      { Peer: {} },
    ]);
    s.claimName
      .mockRejectedValueOnce(new Error("no new tag:gpu-inference device"))
      .mockResolvedValueOnce("100.64.1.3");
    await expect(
      s.provider.bootstrap(await s.provider.describe("pod1"), image, payload),
    ).resolves.toEqual({ ...inventory, tailscale_ip: "100.64.1.3" });
    expect(s.claimName).toHaveBeenCalledTimes(2);
  });

  it("fails if the pod does not re-authenticate as an inference host", async () => {
    const s = tailnetSetup([bootstrapStatus()]);
    await expect(
      s.provider.bootstrap(await s.provider.describe("pod1"), image, payload),
    ).rejects.toThrow("did not re-authenticate");
  });

  it("requires the pod in the tailnet when no legacy public SSH is configured", async () => {
    const s = tailnetSetup([{ Peer: {} }]);
    await expect(s.provider.checkTailscaleEnrollment("pod1")).rejects.toThrow(
      "gpu-bootstrap-pod1 online in the tailnet",
    );
    await expect(s.provider.supportsInPlace!("pod1", image)).resolves.toBe(
      false,
    );
  });

  it("lets an authorized reset re-image a pod that is not in the tailnet", async () => {
    const provider = (minting: boolean) =>
      createRunPodProvider({
        apiKey: "key",
        fetch: fakeRunPod(v5).fetch,
        ...(minting && {
          bootstrapKey: async () => ({
            key: "tskey-auth-bootstrap",
            revoke: async () => {},
          }),
        }),
        tailnet: { run: vi.fn<RunSsh>(), status: async () => ({ Peer: {} }) },
      });
    await expect(
      provider(true).checkTailscaleEnrollment("pod1", { allowReset: true }),
    ).resolves.toBeUndefined();
    await expect(
      provider(true).checkTailscaleEnrollment("pod1"),
    ).rejects.toThrow("authorized reset");
    await expect(
      provider(false).checkTailscaleEnrollment("pod1", { allowReset: true }),
    ).rejects.toThrow("authorized reset");
  });

  it("lets a stopped v5 pod start before it joins the tailnet", async () => {
    const stopped = (env: Record<string, string>) =>
      createRunPodProvider({
        apiKey: "key",
        fetch: fakeRunPod({ ...v5, desiredStatus: "EXITED", env }).fetch,
        tailnet: { run: vi.fn<RunSsh>(), status: async () => ({ Peer: {} }) },
      });
    await expect(
      stopped({
        GRADIATED_TAILSCALE_BOOTSTRAP_KEY:
          "{{ RUNPOD_SECRET_gradiated_tailscale_bootstrap }}",
      }).checkTailscaleEnrollment("pod1"),
    ).resolves.toBeUndefined();
    await expect(
      stopped({ PUBLIC_KEY: "ssh-ed25519 debug" }).checkTailscaleEnrollment(
        "pod1",
      ),
    ).rejects.toThrow("online in the tailnet");
  });

  it("refuses an unenrolled pod on another image", async () => {
    const runpod = fakeRunPod({
      ...v5,
      imageName: "registry.example/other:tag",
    });
    const provider = createRunPodProvider({
      apiKey: "key",
      fetch: runpod.fetch,
      tailnet: { run: vi.fn<RunSsh>(), status: async () => bootstrapStatus() },
    });
    await expect(provider.supportsInPlace!("pod1", image)).rejects.toThrow(
      "approved base image",
    );
  });
});
