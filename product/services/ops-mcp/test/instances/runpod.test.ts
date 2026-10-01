import { describe, expect, it, vi } from "vitest";

import { createRunPodProvider } from "../../src/instances/runpod.js";
import type { RunSsh } from "../../src/instances/ssh.js";
import { fakeRunPod, rtxPod } from "../support/runpod.js";

describe("RunPod provider", () => {
  const image = "registry.example/nomad-base:inputs-abc";
  const runningPod = {
    ...rtxPod,
    desiredStatus: "RUNNING",
    imageName: image,
    publicIp: "157.157.221.177",
    portMappings: { "22": 38187 },
    ports: ["22/tcp", "8888/http"],
  };
  const hostKeys = { pod1: "a".repeat(64) };

  it("enrolls a qualified running pod over SSH without any provider mutation", async () => {
    const runpod = fakeRunPod(runningPod);
    const run = vi.fn<RunSsh>(async () => "");
    const provider = createRunPodProvider({
      apiKey: "key",
      fetch: runpod.fetch,
      inPlace: { run, hostKeys },
    });
    const environment = { GRADIATED_NOMAD_KEY: "private-bootstrap-material" };

    await expect(provider.supportsInPlace!("pod1", image)).resolves.toBe(true);
    await provider.bootstrap(
      await provider.describe("pod1"),
      image,
      environment,
    );

    expect(run).toHaveBeenCalledWith(
      { host: runningPod.publicIp, port: 38187, hostKeySha256: hostKeys.pod1 },
      expect.stringContaining("python3 -c"),
      expect.any(String),
    );
    const payload = JSON.parse(run.mock.calls[0]![2]!);
    expect(payload.environment).toEqual(environment);
    expect(payload.renewalScripts).toEqual({
      agent: expect.stringContaining("def renew_once"),
      supervisor: expect.stringContaining("renew-certificate"),
      startClient: expect.stringContaining("run-renewer"),
    });
    expect(run.mock.calls[0]![1]).not.toContain(
      environment.GRADIATED_NOMAD_KEY,
    );
    expect(runpod.calls.every((call) => call.method === "GET")).toBe(true);
  });

  it.each([
    { imageName: "unqualified:image" },
    { desiredStatus: "CREATED" },
    { ports: ["22/tcp"] },
    { publicIp: null },
    { portMappings: {} },
  ])(
    "refuses in-place enrollment without changing provider configuration: %o",
    async (changes) => {
      const runpod = fakeRunPod({ ...runningPod, ...changes });
      const run = vi.fn(async () => "");
      const provider = createRunPodProvider({
        apiKey: "key",
        fetch: runpod.fetch,
        inPlace: { run, hostKeys },
      });

      await expect(
        provider.bootstrap(await provider.describe("pod1"), image, {}),
      ).rejects.toThrow();

      expect(run).not.toHaveBeenCalled();
      expect(runpod.calls.every((call) => call.method === "GET")).toBe(true);
    },
  );

  it("does not enroll an unpinned host even with SSH configured", async () => {
    const runpod = fakeRunPod(runningPod);
    const run = vi.fn(async () => "");
    const provider = createRunPodProvider({
      apiKey: "key",
      fetch: runpod.fetch,
      inPlace: { run, hostKeys: {} },
    });

    await expect(
      provider.bootstrap(await provider.describe("pod1"), image, {}),
    ).rejects.toThrow("Refusing to reset");
    expect(run).not.toHaveBeenCalled();
    expect(runpod.calls.every((call) => call.method === "GET")).toBe(true);
  });

  it("keeps the stopped-pod provider bootstrap when SSH is configured", async () => {
    const runpod = fakeRunPod({ ...runningPod, desiredStatus: "EXITED" });
    const run = vi.fn(async () => "");
    const provider = createRunPodProvider({
      apiKey: "key",
      fetch: runpod.fetch,
      inPlace: { run, hostKeys },
    });

    await provider.bootstrap(await provider.describe("pod1"), image, {});

    expect(run).not.toHaveBeenCalled();
    expect(runpod.calls.some((call) => call.method === "PATCH")).toBe(true);
    expect(runpod.calls.some((call) => call.url.endsWith("/start"))).toBe(true);
  });

  it("reads an interrupted in-place identity over pinned SSH for resumption", async () => {
    const carried = {
      GRADIATED_INSTANCE_ID: "instance",
      GRADIATED_NOMAD_NODE_ID: "node",
      GRADIATED_NOMAD_NODE_SECRET: "secret",
    };
    const run = vi.fn(async () => JSON.stringify(carried));
    const provider = createRunPodProvider({
      apiKey: "key",
      fetch: fakeRunPod(runningPod).fetch,
      inPlace: { run, hostKeys },
    });

    await expect(provider.environment("pod1")).resolves.toEqual({
      ...rtxPod.env,
      ...carried,
    });
    expect(run).toHaveBeenCalledTimes(1);
  });

  it("reads only provider identity for reset recovery when pinned SSH is unavailable", async () => {
    const run = vi.fn(async () => {
      throw new Error("SSH unavailable");
    });
    const provider = createRunPodProvider({
      apiKey: "key",
      fetch: fakeRunPod(runningPod).fetch,
      inPlace: { run, hostKeys },
    });

    await expect(
      provider.environment("pod1", { providerOnly: true }),
    ).resolves.toEqual(rtxPod.env);
    expect(run).not.toHaveBeenCalled();
    await expect(provider.environment("pod1")).rejects.toThrow(
      "SSH unavailable",
    );
  });

  it.each(["RUNNING", "CREATED", undefined])(
    "refuses reset at status %s before any provider mutation",
    async (desiredStatus) => {
      const runpod = fakeRunPod({ ...rtxPod, desiredStatus });
      const provider = createRunPodProvider({
        apiKey: "key",
        fetch: runpod.fetch,
      });
      const instance = await provider.describe("pod1");

      await expect(
        provider.bootstrap(
          instance,
          "registry.example/nomad-base:inputs-abc",
          {},
        ),
      ).rejects.toThrow("Refusing to reset");
      expect(runpod.calls.every((call) => call.method === "GET")).toBe(true);
    },
  );

  it.each(["RUNNING", "CREATED", undefined])(
    "resets a pod at status %s only when explicitly allowed",
    async (desiredStatus) => {
      const runpod = fakeRunPod({ ...rtxPod, desiredStatus });
      const provider = createRunPodProvider({
        apiKey: "key",
        fetch: runpod.fetch,
      });

      await provider.bootstrap(
        await provider.describe("pod1"),
        "registry.example/nomad-base:inputs-abc",
        {},
        { allowReset: true },
      );

      expect(runpod.calls.some((call) => call.method === "PATCH")).toBe(true);
    },
  );

  it("declares the host proxy port once", async () => {
    const runpod = fakeRunPod({ ...rtxPod, ports: ["22/tcp", "8888/http"] });
    const provider = createRunPodProvider({
      apiKey: "key",
      fetch: runpod.fetch,
    });

    await provider.bootstrap(
      await provider.describe("pod1"),
      "registry.example/nomad-base:inputs-abc",
      {},
    );

    expect(
      runpod.calls.find((call) => call.method === "PATCH")?.body,
    ).toMatchObject({ ports: ["22/tcp", "8888/http"] });
  });

  it.each([
    ["EXITED", true],
    ["RUNNING", false],
    [undefined, false],
  ])(
    "reports a pod at status %s as stopped: %s",
    async (desiredStatus, stopped) => {
      const provider = createRunPodProvider({
        apiKey: "key",
        fetch: fakeRunPod({ ...rtxPod, desiredStatus }).fetch,
      });

      await expect(provider.isStopped("pod1")).resolves.toBe(stopped);
    },
  );

  it("describes a pod as the instance row records it", async () => {
    const runpod = fakeRunPod(rtxPod);
    const provider = createRunPodProvider({
      apiKey: "key",
      fetch: runpod.fetch,
    });

    await expect(provider.describe("pod1")).resolves.toEqual({
      provider: "runpod",
      providerAccountId: "user_1",
      providerInstanceId: "pod1",
      region: "US-NE-1",
      faultDomain: "runpod:machine1",
      sku: "2x NVIDIA RTX PRO 6000 Blackwell Server Edition",
    });
  });

  it("reads the pod's current environment", async () => {
    const runpod = fakeRunPod(rtxPod);
    const provider = createRunPodProvider({
      apiKey: "key",
      fetch: runpod.fetch,
    });

    await expect(provider.environment("pod1")).resolves.toEqual({
      PUBLIC_KEY: "ssh-ed25519 debug",
    });
  });

  it("points the pod at the host image with its bootstrap and keeps other variables", async () => {
    const runpod = fakeRunPod(rtxPod);
    const provider = createRunPodProvider({
      apiKey: "key",
      fetch: runpod.fetch,
    });
    const instance = await provider.describe("pod1");

    await provider.bootstrap(
      instance,
      "registry.example/nomad-base:inputs-abc",
      { GRADIATED_NODE_NAME: "runpod-pod1" },
    );

    expect(runpod.calls.find((call) => call.method === "PATCH")?.body).toEqual({
      imageName: "registry.example/nomad-base:inputs-abc",
      env: {
        PUBLIC_KEY: "ssh-ed25519 debug",
        GRADIATED_NODE_NAME: "runpod-pod1",
      },
      ports: ["22/tcp", "8888/http"],
    });
  });

  it("pulls through the ECR delegation instead of a registry login", async () => {
    const runpod = fakeRunPod(rtxPod);
    const provider = createRunPodProvider({
      apiKey: "key",
      fetch: runpod.fetch,
    });

    await provider.bootstrap(
      await provider.describe("pod1"),
      "registry.example/nomad-base:inputs-abc",
      {},
    );

    expect(
      runpod.calls.map(
        (call) => `${call.method} ${new URL(call.url).pathname}`,
      ),
    ).toEqual([
      "GET /v1/pods/pod1",
      "GET /v1/pods/pod1",
      "PATCH /v1/pods/pod1",
      "POST /v1/pods/pod1/start",
    ]);
  });

  it("leaves starting to the reset when the pod was already running", async () => {
    const runpod = fakeRunPod({ ...rtxPod, desiredStatus: "RUNNING" });
    const provider = createRunPodProvider({
      apiKey: "key",
      fetch: runpod.fetch,
    });

    await provider.bootstrap(
      await provider.describe("pod1"),
      "registry.example/nomad-base:inputs-abc",
      {},
      { allowReset: true },
    );

    expect(runpod.calls.some((call) => call.url.endsWith("/start"))).toBe(
      false,
    );
  });

  it("reports a failed pod update", async () => {
    const runpod = fakeRunPod(rtxPod);
    const failing = (async (input, init) =>
      init?.method === "PATCH"
        ? new Response("no", { status: 500 })
        : runpod.fetch(input, init)) as typeof fetch;
    const provider = createRunPodProvider({ apiKey: "key", fetch: failing });

    await expect(
      provider.bootstrap(
        await provider.describe("pod1"),
        "registry.example/nomad-base:inputs-abc",
        {},
      ),
    ).rejects.toThrow("RunPod PATCH /pods/pod1 failed: 500");
  });
});
