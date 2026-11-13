import { describe, expect, it, vi } from "vitest";
import { createRunPodClient, RunPodError } from "../src/runpod.js";

const wirePod = {
  id: "pod1",
  status: "RUNNING",
  image: "registry.example/gpu:pinned",
  startedAt: "2026-11-13T10:00:00Z",
  env: { MODEL: "example" },
  dataCenterId: "US-TX-1",
  gpu: { id: "NVIDIA B300", count: 8, vcpuCount: 128 },
  mounts: {},
};
const setup = (response: unknown = wirePod, status = 200) => {
  const fetch = vi.fn<typeof globalThis.fetch>(async () =>
    Response.json(response, { status }),
  );
  return {
    fetch,
    client: createRunPodClient({
      apiKey: "private-key",
      userAgent: "gradiated-test",
      fetch,
    }),
  };
};

describe("RunPod REST v2", () => {
  it("reads v2 fields into fleet observations without the removed machine query", async () => {
    const { fetch, client } = setup();
    await expect(client.pod("pod1")).resolves.toEqual({
      id: "pod1",
      desiredStatus: "RUNNING",
      imageName: wirePod.image,
      lastStartedAt: wirePod.startedAt,
      env: wirePod.env,
      gpuCount: 8,
      vcpuCount: 128,
      volumeInGb: 0,
      hasAttachedVolumes: false,
      machine: { dataCenterId: "US-TX-1", gpuTypeId: "NVIDIA B300" },
    });
    expect(fetch).toHaveBeenCalledWith(
      "https://api.runpod.io/v2/pods/pod1",
      expect.objectContaining({
        method: "GET",
        headers: expect.objectContaining({
          authorization: "Bearer private-key",
          "user-agent": "gradiated-test",
        }),
      }),
    );
  });

  it.each(["PROVISIONING", "STARTING", "EXITED", "ERROR", "TERMINATED"])(
    "preserves actual status %s",
    async (status) => {
      const { client } = setup({ ...wirePod, status, startedAt: null });
      expect(await client.pod("pod1")).toMatchObject({
        desiredStatus: status,
        lastStartedAt: null,
      });
    },
  );

  it("reads CPU pods and fractional CPU allocations", async () => {
    const { gpu: _, ...cpuPod } = wirePod;
    const { client } = setup({ ...cpuPod, cpu: { vcpuCount: 2.5 } });
    expect(await client.pod("pod1")).toMatchObject({
      gpuCount: 0,
      vcpuCount: 2.5,
    });
  });

  it.each([
    [{ persistent: { size: 20, path: "/workspace" } }, 20, false],
    [{ network: [{ volumeId: "vol1", path: "/data" }] }, 0, true],
    [{ global: [{ volumeId: "vol2", path: "/data" }] }, 0, true],
  ])(
    "keeps persistent storage visible to lease safety checks (%j)",
    async (mounts, volumeInGb, hasAttachedVolumes) => {
      const { client } = setup({ ...wirePod, mounts });
      expect(await client.pod("pod1")).toMatchObject({
        volumeInGb,
        hasAttachedVolumes,
      });
    },
  );

  it("rejects incomplete observations rather than assuming no persistent storage", async () => {
    const { mounts: _, ...incomplete } = wirePod;
    await expect(setup(incomplete).client.pod("pod1")).rejects.toThrow();
  });

  it("sends image and explicit ports/env in PATCH and start through /action", async () => {
    const { fetch, client } = setup();
    await client.update("pod1", {
      imageName: "new:image",
      ports: [],
      env: { BOOTSTRAP: "private" },
    });
    await client.start("pod1");
    expect(
      fetch.mock.calls.map(([url, init]) => [
        url,
        init?.method,
        JSON.parse(String(init?.body)),
      ]),
    ).toEqual([
      [
        "https://api.runpod.io/v2/pods/pod1",
        "PATCH",
        { image: "new:image", ports: [], env: { BOOTSTRAP: "private" } },
      ],
      [
        "https://api.runpod.io/v2/pods/pod1/action",
        "POST",
        { action: "start" },
      ],
    ]);
  });

  it("uses GraphQL only for account and physical host identity", async () => {
    const { fetch, client } = setup({
      data: { pod: { consumerUserId: "user1", machineId: "machine1" } },
    });
    await expect(client.identity("pod1")).resolves.toEqual({
      consumerUserId: "user1",
      machineId: "machine1",
    });
    expect(fetch).toHaveBeenCalledWith(
      "https://api.runpod.io/graphql",
      expect.objectContaining({ method: "POST" }),
    );
    expect(JSON.parse(String(fetch.mock.calls[0]![1]?.body))).toMatchObject({
      variables: { input: { podId: "pod1" } },
    });
  });

  it("rejects GraphQL errors without leaking their bodies", async () => {
    const { client } = setup({ errors: [{ message: "private credential" }] });
    await expect(client.identity("pod1")).rejects.toThrow(
      "RunPod identity lookup failed",
    );
  });

  it("keeps HTTP status for credential reloads and redacts v2 problem details", async () => {
    const { client } = setup(
      {
        title: "Forbidden",
        status: 403,
        detail: "private credential",
        errors: ["private"],
      },
      403,
    );
    const error = await client.pod("pod1").catch((error: unknown) => error);
    expect(error).toBeInstanceOf(RunPodError);
    expect(error).toMatchObject({
      status: 403,
      message: "RunPod GET /pods/pod1 failed: 403",
    });
  });

  it("validates pod IDs before making requests", async () => {
    const { fetch, client } = setup();
    await expect(client.pod("../pod")).rejects.toThrow();
    await expect(client.identity("../pod")).rejects.toThrow();
    expect(fetch).not.toHaveBeenCalled();
  });
});
