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
  publicIp: "157.157.221.177",
  portMappings: { "22": 38187 },
  ports: ["22/tcp"],
};
const hostKeys = { pod1: "a".repeat(64) };
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
    inPlace: { run, hostKeys },
  });
  return { runpod, run, provider };
};
describe("RunPod Kubernetes enrollment", () => {
  it("checks pinned GPU bootstrap files and installs over SSH without provider mutation", async () => {
    const s = setup();
    await expect(s.provider.supportsInPlace!("pod1", image)).resolves.toBe(
      true,
    );
    const env = { GRADIATED_GPU_BOOTSTRAP: "private-bootstrap-material" };
    await expect(
      s.provider.bootstrap(await s.provider.describe("pod1"), image, env),
    ).resolves.toEqual(inventory);
    expect(s.runpod.calls.every((c) => c.method === "GET")).toBe(true);
    expect(s.run.mock.calls.at(-1)?.[1]).not.toContain(
      env.GRADIATED_GPU_BOOTSTRAP,
    );
    expect(s.run.mock.calls.at(-1)?.[2]).toContain(env.GRADIATED_GPU_BOOTSTRAP);
    expect(s.run.mock.calls.at(-1)?.[0]).toEqual({
      host: running.publicIp,
      port: 38187,
      hostKeySha256: hostKeys.pod1,
    });
  });
  it.each(["RUNNING", "CREATED", "UNKNOWN"])(
    "refuses %s provider reset without explicit authorization",
    async (status) => {
      const s = fakeRunPod({ ...running, desiredStatus: status });
      const provider = createRunPodProvider({ apiKey: "key", fetch: s.fetch });
      await expect(
        provider.bootstrap(await provider.describe("pod1"), image, {}),
      ).rejects.toThrow("Refusing to reset");
      expect(s.calls.every((c) => c.method === "GET")).toBe(true);
    },
  );
  it("requires pinned existing SSH and never changes provider ports", async () => {
    const s = setup({ ...running, ports: ["8888/http"] });
    await expect(s.provider.checkTailscaleEnrollment("pod1")).rejects.toThrow(
      "pinned SSH",
    );
    expect(s.runpod.calls.every((c) => c.method === "GET")).toBe(true);
  });
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
      inPlace: { run: s.run, hostKeys },
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
      inPlace: { run: s.run, hostKeys },
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
