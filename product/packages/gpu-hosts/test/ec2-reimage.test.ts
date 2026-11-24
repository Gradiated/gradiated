import { describe, expect, it } from "vitest";

import type { AwsGpuClient, Ec2Instance } from "../src/aws.js";
import {
  ec2Refusal,
  prepareReplacement,
  removeBootstrapAccess,
  replacementProgress,
} from "../src/ec2-reimage.js";

const instance = (fields: Partial<Ec2Instance> = {}): Ec2Instance => ({
  id: "i-0123456789abcdef0",
  accountId: "111122223333",
  state: "running",
  availabilityZone: "us-east-1b",
  instanceType: "g6.xlarge",
  imageId: "ami-0abc",
  tags: { "gradiated:managed": "gpu-fleet" },
  ...fields,
});

describe("EC2 re-imaging", () => {
  it("refuses an untagged instance and one in another account", () => {
    expect(ec2Refusal(instance(), "111122223333")).toBeUndefined();
    expect(ec2Refusal(instance({ tags: {} }), "111122223333")).toBe(
      "EC2 instance i-0123456789abcdef0 is not tagged gradiated:managed=gpu-fleet, so the GPU fleet cannot manage it",
    );
    expect(ec2Refusal(instance(), "444455556666")).toBe(
      "EC2 instance i-0123456789abcdef0 is in account 111122223333, not 444455556666",
    );
  });

  describe("before a root volume is replaced", () => {
    const client = (fields: { profile?: boolean; readable?: boolean }) => {
      const calls: string[] = [];
      let profile = fields.profile ?? false;
      return {
        calls,
        client: {
          deleteBootstrapSecret: async () => {
            calls.push("deleteBootstrapSecret");
            return true;
          },
          bootstrapSecretReadable: async () => fields.readable ?? false,
          disassociateBootstrapProfile: async () => {
            calls.push("disassociateBootstrapProfile");
            const removed = profile ? 1 : 0;
            profile = false;
            return { removed, kept: [] };
          },
          associateBootstrapProfile: async () => {
            calls.push("associateBootstrapProfile");
            return true;
          },
        } as unknown as AwsGpuClient,
      };
    };

    it("deletes the secret and removes the bootstrap profile, never attaching one", async () => {
      const s = client({ profile: true });
      await expect(prepareReplacement(s.client, instance())).resolves.toBe(
        true,
      );
      expect(s.calls).toEqual([
        "deleteBootstrapSecret",
        "disassociateBootstrapProfile",
      ]);

      const bare = client({});
      await expect(prepareReplacement(bare.client, instance())).resolves.toBe(
        false,
      );
      expect(bare.calls).toEqual([
        "deleteBootstrapSecret",
        "disassociateBootstrapProfile",
      ]);
    });

    it("refuses while the secret is readable or another profile is attached", async () => {
      await expect(
        prepareReplacement(client({ readable: true }).client, instance()),
      ).rejects.toThrow("still readable");
      const other = client({});
      await expect(
        prepareReplacement(
          other.client,
          instance({
            instanceProfileArn:
              "arn:aws:iam::111122223333:instance-profile/other",
          }),
        ),
      ).rejects.toThrow("instance-profile/other");
      expect(other.calls).toEqual([
        "deleteBootstrapSecret",
        "disassociateBootstrapProfile",
      ]);
    });
  });

  it("tells which replacements are in flight and which ended last", async () => {
    const client = {
      replaceRootVolumeTasks: async () => [
        { id: "replacevol-1", state: "failed" },
        { id: "replacevol-2", state: "in-progress" },
      ],
    } as unknown as AwsGpuClient;

    expect(await replacementProgress(client, "i-0123456789abcdef0")).toEqual({
      inFlight: [{ id: "replacevol-2", state: "in-progress" }],
      last: { id: "replacevol-2", state: "in-progress" },
    });
  });

  it("tries to remove both the secret and the profile, and says what is left", async () => {
    const calls: string[] = [];
    const client = {
      deleteBootstrapSecret: async () => {
        calls.push("secret");
        throw new Error("AccessDenied");
      },
      disassociateBootstrapProfile: async () => {
        calls.push("profile");
        return {
          removed: 0,
          kept: ["arn:aws:iam::111122223333:instance-profile/other"],
        };
      },
    } as unknown as AwsGpuClient;

    expect(await removeBootstrapAccess(client, "i-0123456789abcdef0")).toEqual({
      left: ["its bootstrap secret"],
      kept: ["arn:aws:iam::111122223333:instance-profile/other"],
    });
    expect(calls).toEqual(["secret", "profile"]);
  });
});
