import type { AwsGpuClient, RunPod, RunPodClient } from "@gradiated/gpu-hosts";
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

describe("reaching an AWS host", () => {
  const ec2Host = (accountId: string, region = "us-east-1") =>
    ({
      metadata: { name: "gpu-x", uid: "u1" },
      spec: {
        ...host.spec,
        provider: {
          name: "aws",
          accountId,
          region,
          availabilityZone: `${region}b`,
          ec2InstanceId: "i-0123456789abcdef0",
        },
      },
    }) as unknown as GpuHost;
  const client = (accountId: string, owner = accountId) => {
    const calls: string[] = [];
    const fake = {
      accountId,
      region: "us-east-1",
      instance: async (id: string) => {
        calls.push(`instance ${id}`);
        return {
          id,
          accountId: owner,
          state: "running",
          tags: { "gradiated:managed": "gpu-fleet" },
        };
      },
      deleteBootstrapSecret: async () => {
        calls.push("deleteBootstrapSecret");
        return false;
      },
      bootstrapSecretReadable: async () => false,
      bootstrapProfileAssociated: async () => false,
      disassociateBootstrapProfile: async () => ({ removed: 0, kept: [] }),
      associateBootstrapProfile: async () => {
        calls.push("associateBootstrapProfile");
        return true;
      },
      launchTemplateImage: async () => "ami-0fedcba9876543210",
      replaceRootVolume: async (_id: string, token: string) => {
        calls.push(`replaceRootVolume ${token}`);
        return { id: "replacevol-1", state: "pending" };
      },
    } as unknown as AwsGpuClient;
    return { calls, fake };
  };
  const using = (fake: AwsGpuClient) =>
    createEnrollment({
      aws: (accountId: string) =>
        accountId === fake.accountId ? fake : undefined,
    } as unknown as Parameters<typeof createEnrollment>[0]);

  it("uses only the client of the host's own account and region", async () => {
    const ours = client("111122223333");
    const enrollment = using(ours.fake);

    await enrollment.instance(ec2Host("111122223333"));
    expect(ours.calls).toEqual(["instance i-0123456789abcdef0"]);
    await expect(enrollment.instance(ec2Host("444455556666"))).rejects.toThrow(
      "AWS access to account 444455556666 is not configured",
    );
    await expect(
      enrollment.instance(ec2Host("111122223333", "us-west-2")),
    ).rejects.toThrow("is for us-east-1, not us-west-2");
  });

  it("refuses an instance another account owns before touching its root", async () => {
    const theirs = client("111122223333", "444455556666");
    const enrollment = using(theirs.fake);

    expect(await enrollment.ec2Refusal(ec2Host("111122223333"))).toBe(
      "EC2 instance i-0123456789abcdef0 is in account 444455556666, not 111122223333",
    );
    await expect(
      enrollment.replaceRoot(ec2Host("111122223333"), "2026-11-23T12:00:00Z"),
    ).rejects.toThrow("is in account 444455556666");
    expect(theirs.calls).toEqual([
      "instance i-0123456789abcdef0",
      "instance i-0123456789abcdef0",
    ]);
  });

  it("sends a repeated replace request with the same client token", async () => {
    const ours = client("111122223333");
    const enrollment = using(ours.fake);
    const target = ec2Host("111122223333");

    await enrollment.replaceRoot(target, "2026-11-23T12:00:00.000Z");
    await enrollment.replaceRoot(target, "2026-11-23T12:00:00.000Z");
    await enrollment.replaceRoot(target, "2026-11-23T13:00:00.000Z");

    const tokens = ours.calls
      .filter((call) => call.startsWith("replaceRootVolume"))
      .map((call) => call.split(" ")[1]);
    expect(tokens[0]).toBe(tokens[1]);
    expect(tokens[2]).not.toBe(tokens[0]);
    expect(tokens[0]).toMatch(/^[0-9a-f]{64}$/);
  });
});
