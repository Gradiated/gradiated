import { EC2Client } from "@aws-sdk/client-ec2";
import { SecretsManagerClient } from "@aws-sdk/client-secrets-manager";
import { describe, expect, it, vi } from "vitest";

import {
  bootstrapSecretName,
  createAwsGpuClient,
  isManaged,
  replacementSettled,
} from "../src/aws.js";

const access = {
  region: "us-east-1",
  roleArn: "arn:aws:iam::111122223333:role/gradiated-gpu-fleet-operator",
  bootstrapInstanceProfile: "gradiated-gpu-prod-host-bootstrap",
  secretKmsKeyId: "alias/gradiated-gpu-prod",
  sessionName: "gradiated-test",
};
const ID = "i-0123456789abcdef0";

type Sent = { name: string; input: Record<string, unknown> };

const setup = (
  answer: (sent: Sent) => unknown = () => ({}),
  clock?: { sleep: (ms: number) => Promise<void>; now: () => number },
): { sent: Sent[]; client: ReturnType<typeof createAwsGpuClient> } => {
  const sent: Sent[] = [];
  const ec2 = new EC2Client({ region: "us-east-1" });
  const secrets = new SecretsManagerClient({ region: "us-east-1" });
  for (const client of [ec2, secrets])
    vi.spyOn(client, "send").mockImplementation((async (command: {
      constructor: { name: string };
      input: Record<string, unknown>;
    }) => {
      const call = { name: command.constructor.name, input: command.input };
      sent.push(call);
      return answer(call);
    }) as never);
  return {
    sent,
    client: createAwsGpuClient({ access, ec2, secrets, ...clock }),
  };
};

const failure = (name: string) => {
  const error = new Error(name);
  error.name = name;
  return error;
};

// A clock that advances only when the client sleeps.
const fakeClock = () => {
  const clock = {
    time: 0,
    waits: [] as number[],
    now: () => clock.time,
    sleep: async (ms: number) => {
      clock.waits.push(ms);
      clock.time += ms;
    },
  };
  return clock;
};

const BOOTSTRAP_PROFILE_ARN =
  "arn:aws:iam::111122223333:instance-profile/gradiated-gpu-prod-host-bootstrap";

const described = {
  Reservations: [
    {
      OwnerId: "111122223333",
      Instances: [
        {
          InstanceId: ID,
          State: { Name: "running" },
          Placement: { AvailabilityZone: "us-east-1b" },
          InstanceType: "g6.xlarge",
          ImageId: "ami-0abc",
          LaunchTime: new Date("2026-11-20T10:00:00Z"),
          Tags: [
            { Key: "gradiated:managed", Value: "gpu-fleet" },
            { Key: "aws:ec2launchtemplate:id", Value: "lt-0abc" },
            { Key: "aws:ec2launchtemplate:version", Value: "3" },
          ],
          IamInstanceProfile: {
            Arn: "arn:aws:iam::111122223333:instance-profile/gradiated-gpu-prod-host-bootstrap",
          },
        },
      ],
    },
  ],
};

describe("EC2 GPU hosts", () => {
  it("describes an instance with its zone, type, launch template and tags", async () => {
    const { client } = setup(() => described);
    const instance = await client.instance(ID);
    expect(instance).toEqual({
      id: ID,
      accountId: "111122223333",
      state: "running",
      availabilityZone: "us-east-1b",
      instanceType: "g6.xlarge",
      imageId: "ami-0abc",
      launchTemplate: { id: "lt-0abc", version: "3" },
      launchedAt: "2026-11-20T10:00:00.000Z",
      tags: {
        "gradiated:managed": "gpu-fleet",
        "aws:ec2launchtemplate:id": "lt-0abc",
        "aws:ec2launchtemplate:version": "3",
      },
      instanceProfileArn:
        "arn:aws:iam::111122223333:instance-profile/gradiated-gpu-prod-host-bootstrap",
    });
    expect(isManaged(instance)).toBe(true);
    expect(client.accountId).toBe("111122223333");
  });

  it("refuses IDs that are not EC2 instance IDs before calling AWS", async () => {
    const { sent, client } = setup(() => described);
    for (const id of ["pod1", "i-XYZ", "i-0123abc", "i-0123456789abcdef0/x"])
      await expect(client.instance(id)).rejects.toThrow();
    expect(() => bootstrapSecretName("../other")).toThrow();
    expect(sent).toEqual([]);
  });

  it("knows the GPUs of the fleet's instance families without asking EC2", async () => {
    const { sent, client } = setup();
    for (const [type, gpus] of [
      ["g6.xlarge", { count: 1, name: "L4" }],
      ["g6.16xlarge", { count: 1, name: "L4" }],
      ["g6.12xlarge", { count: 4, name: "L4" }],
      ["g6.48xlarge", { count: 8, name: "L4" }],
      ["g6e.2xlarge", { count: 1, name: "L40S" }],
    ] as const)
      await expect(client.gpus(type)).resolves.toEqual(gpus);
    expect(sent).toEqual([]);
  });

  it("reads one kind of GPU from any other instance type", async () => {
    const { client } = setup(() => ({
      InstanceTypes: [
        {
          GpuInfo: {
            Gpus: [{ Name: "H100", Manufacturer: "NVIDIA", Count: 8 }],
          },
        },
      ],
    }));
    await expect(client.gpus("p5.48xlarge")).resolves.toEqual({
      count: 8,
      name: "H100",
    });
    const none = setup(() => ({ InstanceTypes: [{}] }));
    await expect(none.client.gpus("m7i.large")).rejects.toThrow(
      "no single kind of GPU",
    );
  });

  it("restores the root volume from the given AMI and deletes the old one", async () => {
    const { sent, client } = setup(({ name }) =>
      name === "CreateReplaceRootVolumeTaskCommand"
        ? {
            ReplaceRootVolumeTask: {
              ReplaceRootVolumeTaskId: "replacevol-1",
              TaskState: "pending",
            },
          }
        : {
            ReplaceRootVolumeTasks: [
              {
                ReplaceRootVolumeTaskId: "replacevol-1",
                TaskState: "succeeded",
              },
            ],
          },
    );
    await expect(
      client.replaceRootVolume(ID, "key-1", "ami-0123456789abcdef0"),
    ).resolves.toEqual({
      id: "replacevol-1",
      state: "pending",
    });
    await expect(
      client.replaceRootVolumeTask(ID, "replacevol-1"),
    ).resolves.toEqual({ id: "replacevol-1", state: "succeeded" });
    // Named explicitly: without an image EC2 restores the original launch AMI.
    expect(sent[0]).toEqual({
      name: "CreateReplaceRootVolumeTaskCommand",
      input: {
        InstanceId: ID,
        ImageId: "ami-0123456789abcdef0",
        DeleteReplacedRootVolume: true,
        ClientToken: "key-1",
      },
    });
    await expect(
      client.replaceRootVolume(ID, "key-2", "resolve:ssm:/ami"),
    ).rejects.toThrow();
  });

  it("lists every replace-root-volume task of an instance across pages, oldest first", async () => {
    const { sent, client } = setup(({ input }) =>
      input.NextToken
        ? {
            ReplaceRootVolumeTasks: [
              {
                ReplaceRootVolumeTaskId: "replacevol-1",
                TaskState: "succeeded",
                StartTime: "2026-11-19T10:00:00.000Z",
              },
            ],
          }
        : {
            ReplaceRootVolumeTasks: [
              {
                ReplaceRootVolumeTaskId: "replacevol-2",
                TaskState: "in-progress",
                StartTime: "2026-11-20T10:00:00.000Z",
              },
            ],
            NextToken: "page-2",
          },
    );
    const tasks = await client.replaceRootVolumeTasks(ID);
    expect(tasks).toEqual([
      {
        id: "replacevol-1",
        state: "succeeded",
        started: new Date("2026-11-19T10:00:00.000Z"),
      },
      {
        id: "replacevol-2",
        state: "in-progress",
        started: new Date("2026-11-20T10:00:00.000Z"),
      },
    ]);
    expect(tasks.map(replacementSettled)).toEqual([true, false]);
    expect(sent).toEqual([
      {
        name: "DescribeReplaceRootVolumeTasksCommand",
        input: {
          Filters: [{ Name: "instance-id", Values: [ID] }],
          MaxResults: 50,
          NextToken: undefined,
        },
      },
      {
        name: "DescribeReplaceRootVolumeTasksCommand",
        input: {
          Filters: [{ Name: "instance-id", Values: [ID] }],
          MaxResults: 50,
          NextToken: "page-2",
        },
      },
    ]);
    await expect(client.replaceRootVolumeTasks("i-nope")).rejects.toThrow();
  });

  it("reads the AMI from the launch template's default version", async () => {
    const { sent, client } = setup(() => ({
      LaunchTemplateVersions: [
        {
          VersionNumber: 4,
          DefaultVersion: true,
          LaunchTemplateData: { ImageId: "ami-0fedcba9876543210" },
        },
      ],
    }));
    await expect(client.launchTemplateImage()).resolves.toBe(
      "ami-0fedcba9876543210",
    );
    expect(sent).toEqual([
      {
        name: "DescribeLaunchTemplateVersionsCommand",
        input: {
          LaunchTemplateName: "gradiated-gpu-prod-host",
          Versions: ["$Default"],
        },
      },
    ]);

    const ec2 = new EC2Client({ region: "us-east-1" });
    const send = vi.spyOn(ec2, "send").mockResolvedValue({
      LaunchTemplateVersions: [
        { LaunchTemplateData: { ImageId: "ami-0fedcba9876543210" } },
      ],
    } as never);
    await createAwsGpuClient({
      access: { ...access, launchTemplateName: "other-host" },
      ec2,
      secrets: new SecretsManagerClient({ region: "us-east-1" }),
    }).launchTemplateImage();
    expect(
      (send.mock.calls[0]![0] as unknown as { input: Record<string, unknown> })
        .input,
    ).toMatchObject({ LaunchTemplateName: "other-host" });
    const other = setup(() => ({ LaunchTemplateVersions: [] }));
    await expect(other.client.launchTemplateImage()).rejects.toThrow(
      "has no default version",
    );
    const noImage = setup(() => ({
      LaunchTemplateVersions: [{ LaunchTemplateData: {} }],
    }));
    await expect(noImage.client.launchTemplateImage()).rejects.toThrow(
      "names no AMI",
    );
  });

  it("tells whether the bootstrap instance profile is associated", async () => {
    const associated = setup(() => ({
      IamInstanceProfileAssociations: [
        {
          AssociationId: "iip-assoc-1",
          IamInstanceProfile: {
            Arn: "arn:aws:iam::111122223333:instance-profile/gradiated-gpu-prod-host-bootstrap",
          },
        },
      ],
    }));
    await expect(
      associated.client.bootstrapProfileAssociated(ID),
    ).resolves.toBe(true);
    const other = setup(() => ({
      IamInstanceProfileAssociations: [
        {
          AssociationId: "iip-assoc-1",
          IamInstanceProfile: {
            Arn: "arn:aws:iam::111122223333:instance-profile/something-else",
          },
        },
      ],
    }));
    await expect(other.client.bootstrapProfileAssociated(ID)).resolves.toBe(
      false,
    );
    const none = setup(() => ({ IamInstanceProfileAssociations: [] }));
    await expect(none.client.bootstrapProfileAssociated(ID)).resolves.toBe(
      false,
    );
  });

  it("writes the bootstrap secret encrypted, tagged with the instance ARN, and overwrites an existing one", async () => {
    let exists = false;
    const { sent, client } = setup(({ name }) => {
      if (name === "CreateSecretCommand" && exists) {
        const error = new Error("exists");
        error.name = "ResourceExistsException";
        throw error;
      }
      exists = true;
      return {};
    });
    const value = {
      image:
        "873716897517.dkr.ecr.us-east-1.amazonaws.com/gradiated/prod/inference:gpu-base-inputs-abc",
      tailscaleAuthKey: "tskey-auth-bootstrap",
    };
    await client.writeBootstrapSecret(ID, value);
    await client.writeBootstrapSecret(ID, value);
    const secret = JSON.stringify({
      image: value.image,
      tailscale_auth_key: value.tailscaleAuthKey,
    });
    expect(sent).toEqual([
      {
        name: "CreateSecretCommand",
        input: {
          Name: `gradiated/gpu-bootstrap/${ID}`,
          SecretString: secret,
          KmsKeyId: "alias/gradiated-gpu-prod",
          Tags: [
            {
              Key: "gradiated:instance-arn",
              Value: `arn:aws:ec2:us-east-1:111122223333:instance/${ID}`,
            },
            { Key: "Project", Value: "gradiated" },
            { Key: "Environment", Value: "prod" },
          ],
        },
      },
      expect.objectContaining({ name: "CreateSecretCommand" }),
      {
        name: "DescribeSecretCommand",
        input: { SecretId: `gradiated/gpu-bootstrap/${ID}` },
      },
      {
        name: "PutSecretValueCommand",
        input: {
          SecretId: `gradiated/gpu-bootstrap/${ID}`,
          SecretString: secret,
        },
      },
    ]);
    await expect(
      client.writeBootstrapSecret(ID, { ...value, tailscaleAuthKey: "nope" }),
    ).rejects.toThrow();
  });

  it("waits for a forced deletion in progress to finish, then creates the secret, never restoring it", async () => {
    const clock = fakeClock();
    const { sent, client } = setup(({ name }) => {
      const deleting = clock.time < 4_000;
      if (name === "CreateSecretCommand" && deleting)
        throw failure("ResourceExistsException");
      if (name === "DescribeSecretCommand")
        return deleting
          ? { DeletedDate: new Date("2026-11-20T10:00:00Z") }
          : {};
      // Secrets Manager rejects a value for a secret pending deletion.
      if (name === "PutSecretValueCommand")
        throw failure("InvalidRequestException");
      return {};
    }, clock);
    const value = {
      image: "registry.example/gpu-base:abc",
      tailscaleAuthKey: "tskey-auth-bootstrap",
    };
    await client.writeBootstrapSecret(ID, value);
    expect(sent.map(({ name }) => name)).toEqual([
      "CreateSecretCommand",
      "DescribeSecretCommand",
      "CreateSecretCommand",
      "DescribeSecretCommand",
      "CreateSecretCommand",
      "DescribeSecretCommand",
      "CreateSecretCommand",
    ]);
    expect(clock.waits).toEqual([1_000, 2_000, 5_000]);

    // Bounded: a deletion that never finishes fails the write within about
    // two minutes, without overwriting or restoring the pending secret.
    const stuck = fakeClock();
    const forever = setup(({ name }) => {
      if (name === "CreateSecretCommand")
        throw failure("ResourceExistsException");
      if (name === "DescribeSecretCommand")
        return { DeletedDate: new Date("2026-11-20T10:00:00Z") };
      return {};
    }, stuck);
    await expect(
      forever.client.writeBootstrapSecret(ID, value),
    ).rejects.toThrow("still being deleted");
    expect(stuck.time).toBeLessThanOrEqual(2 * 60_000);
    expect(stuck.time).toBeGreaterThan(60_000);
    expect(
      forever.sent.filter(
        ({ name }) =>
          name !== "CreateSecretCommand" && name !== "DescribeSecretCommand",
      ),
    ).toEqual([]);

    // Deleted between the create and the describe: created again at once.
    let gone = false;
    const raced = setup(({ name }) => {
      if (name === "CreateSecretCommand" && !gone)
        throw failure("ResourceExistsException");
      if (name === "DescribeSecretCommand") {
        gone = true;
        throw failure("ResourceNotFoundException");
      }
      return {};
    }, fakeClock());
    await raced.client.writeBootstrapSecret(ID, value);
    expect(raced.sent.map(({ name }) => name)).toEqual([
      "CreateSecretCommand",
      "DescribeSecretCommand",
      "CreateSecretCommand",
    ]);
  });

  it("force-deletes the bootstrap secret and treats a missing one as deleted", async () => {
    let calls = 0;
    const { sent, client } = setup(() => {
      if (calls++) {
        const error = new Error("gone");
        error.name = "ResourceNotFoundException";
        throw error;
      }
      return {};
    });
    await expect(client.deleteBootstrapSecret(ID)).resolves.toBe(true);
    await expect(client.deleteBootstrapSecret(ID)).resolves.toBe(false);
    expect(sent[0]).toEqual({
      name: "DeleteSecretCommand",
      input: {
        SecretId: `gradiated/gpu-bootstrap/${ID}`,
        ForceDeleteWithoutRecovery: true,
      },
    });
  });

  it("associates the bootstrap profile only when the instance has none, and removes every association", async () => {
    let associated: {
      AssociationId: string;
      IamInstanceProfile: { Arn: string };
    }[] = [];
    const { sent, client } = setup(({ name }) => {
      if (name === "DescribeIamInstanceProfileAssociationsCommand")
        return { IamInstanceProfileAssociations: associated };
      if (name === "AssociateIamInstanceProfileCommand")
        associated = [
          {
            AssociationId: "iip-assoc-1",
            IamInstanceProfile: { Arn: BOOTSTRAP_PROFILE_ARN },
          },
        ];
      return {};
    });
    await expect(client.associateBootstrapProfile(ID)).resolves.toBe(true);
    await expect(client.associateBootstrapProfile(ID)).resolves.toBe(false);
    await expect(client.disassociateInstanceProfile(ID)).resolves.toBe(1);
    expect(sent.filter(({ name }) => !name.startsWith("Describe"))).toEqual([
      {
        name: "AssociateIamInstanceProfileCommand",
        input: {
          InstanceId: ID,
          IamInstanceProfile: { Name: "gradiated-gpu-prod-host-bootstrap" },
        },
      },
      {
        name: "DisassociateIamInstanceProfileCommand",
        input: { AssociationId: "iip-assoc-1" },
      },
    ]);
  });

  it("accepts the bootstrap profile already associated and refuses any other profile", async () => {
    const withProfile = (Arn: string) =>
      setup(({ name }) =>
        name === "DescribeIamInstanceProfileAssociationsCommand"
          ? {
              IamInstanceProfileAssociations: [
                { AssociationId: "iip-assoc-1", IamInstanceProfile: { Arn } },
              ],
            }
          : {},
      );
    const bootstrap = withProfile(BOOTSTRAP_PROFILE_ARN);
    await expect(bootstrap.client.associateBootstrapProfile(ID)).resolves.toBe(
      false,
    );
    const other = withProfile(
      "arn:aws:iam::111122223333:instance-profile/something-else",
    );
    await expect(other.client.associateBootstrapProfile(ID)).rejects.toThrow(
      "instance-profile/something-else, not gradiated-gpu-prod-host-bootstrap",
    );
    for (const { sent } of [bootstrap, other])
      expect(sent.map(({ name }) => name)).toEqual([
        "DescribeIamInstanceProfileAssociationsCommand",
      ]);
  });
});
