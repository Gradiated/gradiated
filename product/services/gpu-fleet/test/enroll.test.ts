import type { RunPod, RunPodClient } from "@gradiated/gpu-hosts";
import { describe, expect, it } from "vitest";

import { createEnrollment } from "../src/enroll.js";
import type { GpuHost } from "../src/hosts.js";

const host = {
  metadata: { name: "gpu-019d5a4a-0000-7000-8000-000000000001" },
  spec: {
    instanceId: "019d5a4a-0000-7000-8000-000000000001",
    provider: { name: "runpod", accountId: "user_test", podId: "pod1" },
    inventory: { gpuProduct: "B300", gpuCount: 4, cpu: 64, memoryGiB: 896 },
    managementSecret: { key: "gradiated/prod/platform/gpu-host/x" },
  },
} as unknown as GpuHost;

// A pod whose environment the next re-image starts from.
const runpod = (env: Record<string, string>) => {
  const pod = {
    id: "pod1",
    consumerUserId: "user_test",
    machineId: "m1",
    gpuCount: 4,
    vcpuCount: 64,
    desiredStatus: "RUNNING",
    imageName: "old",
    env,
    machine: {},
  } as RunPod;
  const client = {
    pod: async () => structuredClone(pod),
    update: async (_podId: string, body: Record<string, unknown>) => {
      pod.imageName = body.imageName as string;
      pod.env = body.env as Record<string, string>;
    },
    start: async () => undefined,
  } as unknown as RunPodClient;
  return { pod, client };
};

describe("re-imaging a pod", () => {
  it("never carries Tailscale settings it did not set into the new container", async () => {
    const { pod, client } = runpod({
      GRADIATED_TAILSCALE_LOGIN_SERVER: "https://attacker.example",
      GRADIATED_TAILSCALE_BOOTSTRAP_KEY: "tskey-auth-stale",
      PUBLIC_KEY: "ssh-ed25519 AAAA",
      HF_TOKEN_SECRET_NAME: "kept",
    });
    const enrollment = createEnrollment({
      runpod: client,
    } as unknown as Parameters<typeof createEnrollment>[0]);

    await enrollment.reimage(host, "new", "tskey-auth-fresh");

    expect(pod.imageName).toBe("new");
    expect(pod.env).toEqual({
      HF_TOKEN_SECRET_NAME: "kept",
      GRADIATED_TAILSCALE_BOOTSTRAP_KEY: "tskey-auth-fresh",
    });
  });
});
