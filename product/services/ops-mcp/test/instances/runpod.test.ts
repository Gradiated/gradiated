import { describe, expect, it, vi } from "vitest";
import { createRunPodProvider } from "../../src/instances/runpod.js";
import type { RunSsh } from "../../src/instances/ssh.js";
import { fakeRunPod, rtxPod } from "../support/runpod.js";
const image = "registry.example/gpu-base:pinned";
const inventory = {
  tailscaleIp: "100.64.0.1",
  gpuCount: 2,
  gpuProduct: "RTX-PRO-6000",
  cpu: 28,
  memoryGiB: 112,
};
const running = {
  ...rtxPod,
  desiredStatus: "RUNNING",
  imageName: image,
};
const setup = (pod = running) => {
  const runpod = fakeRunPod(pod);
  const run = vi.fn<RunSsh>(async (_target, command) =>
    command.includes("GRADIATED_INSTANCE_ID")
      ? "{}"
      : command.includes("files=json.load")
        ? "qualified"
        : JSON.stringify(inventory),
  );
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
        provider.bootstrap(await provider.describe("pod1"), image, {}),
      ).rejects.toThrow("Refusing to reset");
      expect(s.calls.every((c) => c.method === "GET")).toBe(true);
    },
  );
  it("configures and starts a stopped pod, preserves SSH key, and uses ECR delegation", async () => {
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
    const provider = createRunPodProvider({
      apiKey: "key",
      fetch,
      tailnet: { run: s.run, status: async () => bootstrapStatus() },
    });
    const env = { GRADIATED_GPU_BOOTSTRAP: "private-encoded-bootstrap" };
    await provider.bootstrap(await provider.describe("pod1"), image, env);
    const patch = fetch.mock.calls.find(
      ([, init]) => init?.method === "PATCH",
    )![1]!;
    expect(JSON.parse(String(patch.body))).toEqual({
      imageName: image,
      env: { PUBLIC_KEY: rtxPod.env.PUBLIC_KEY },
    });
    expect(
      fetch.mock.calls.some(([url]) => String(url).endsWith("/start")),
    ).toBe(true);
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
      provider.bootstrap(
        await provider.describe("pod1"),
        image,
        {},
        { allowReset: true },
      ),
    ).rejects.toThrow("RunPod PATCH /pods/pod1 failed: 500");
    await expect(
      provider.bootstrap(
        await provider.describe("pod1"),
        image,
        {},
        { allowReset: true },
      ),
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
    const run = vi.fn<RunSsh>(async (_target, command) =>
      command.includes("GRADIATED_INSTANCE_ID")
        ? "{}"
        : command.includes("files=json.load")
          ? "qualified"
          : JSON.stringify({
              ...inventory,
              tailscaleIp: "100.64.0.9",
              promotion: true,
            }),
    );
    const provider = createRunPodProvider({
      apiKey: "private-api-key",
      fetch: runpod.fetch,
      tailnet: { run, status, promotionTimeoutMs: 300, promotionPollMs: 10 },
    });
    return { runpod, run, status, provider };
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
    const env = { GRADIATED_GPU_BOOTSTRAP: "private-bootstrap-material" };
    await expect(
      s.provider.bootstrap(await s.provider.describe("pod1"), image, env),
    ).resolves.toEqual({ ...inventory, tailscaleIp: "100.64.0.9" });
    expect(s.runpod.calls.every((c) => c.method === "GET")).toBe(true);
    const [target, command, input] = s.run.mock.calls.at(-1)!;
    expect(target.host).toBe("100.64.0.9");
    expect(target.port).toBe(22);
    expect([target.hostKeySha256].flat()).toHaveLength(1);
    expect(command).not.toContain(env.GRADIATED_GPU_BOOTSTRAP);
    expect(input).toContain(env.GRADIATED_GPU_BOOTSTRAP);
  });

  it("fails if the pod does not re-authenticate as an inference host", async () => {
    const s = tailnetSetup([bootstrapStatus()]);
    await expect(
      s.provider.bootstrap(await s.provider.describe("pod1"), image, {}),
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
      tailnet: {
        run: vi.fn<RunSsh>(async () => "{}"),
        status: async () => bootstrapStatus(),
      },
    });
    await expect(provider.supportsInPlace!("pod1", image)).rejects.toThrow(
      "approved base image",
    );
  });
});
