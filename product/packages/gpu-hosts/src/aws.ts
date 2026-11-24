import {
  AssociateIamInstanceProfileCommand,
  CreateReplaceRootVolumeTaskCommand,
  DescribeIamInstanceProfileAssociationsCommand,
  DescribeInstancesCommand,
  DescribeInstanceTypesCommand,
  DescribeLaunchTemplateVersionsCommand,
  DescribeReplaceRootVolumeTasksCommand,
  DisassociateIamInstanceProfileCommand,
  EC2Client,
  StartInstancesCommand,
  type _InstanceType,
} from "@aws-sdk/client-ec2";
import {
  CreateSecretCommand,
  DeleteSecretCommand,
  DescribeSecretCommand,
  PutSecretValueCommand,
  SecretsManagerClient,
} from "@aws-sdk/client-secrets-manager";
import { fromTemporaryCredentials } from "@aws-sdk/credential-providers";
import { z } from "zod";

import { EC2_INSTANCE_ID } from "./ids.js";

// AWS GPU hosts are EC2 instances in the GPU member account. The prod
// gpu-fleet and ops-mcp roles reach them only through the account's
// gradiated-gpu-fleet-operator role, which may start an instance, replace its
// root volume and change its instance profile, and only on instances tagged
// gradiated:managed=gpu-fleet. It cannot terminate, stop, run or modify one.
export const MANAGED_TAG = { key: "gradiated:managed", value: "gpu-fleet" };

// The host launcher (launch template user-data, outside the container) reads
// this secret with the instance's bootstrap profile, then starts the GPU base
// image with the key as GRADIATED_TAILSCALE_BOOTSTRAP_KEY and the instance ID
// as GRADIATED_PROVIDER_INSTANCE_ID. It runs only on a fresh root volume.
export const bootstrapSecretName = (instanceId: string) =>
  `gradiated/gpu-bootstrap/${ec2InstanceId.parse(instanceId)}`;

export const ec2InstanceId = z.string().regex(EC2_INSTANCE_ID);

export const DEFAULT_LAUNCH_TEMPLATE = "gradiated-gpu-prod-host";

const amiId = z.string().regex(/^ami-[0-9a-f]{8,17}$/);

export type AwsGpuAccess = {
  readonly region: string;
  // arn:aws:iam::<GPU account>:role/gradiated-gpu-fleet-operator, assumed
  // with the caller's own (pod identity) credentials.
  readonly roleArn: string;
  // The instance profile a re-imaged host reads its bootstrap secret with;
  // removed once the host is enrolled.
  readonly bootstrapInstanceProfile: string;
  // The launch template whose default version names the AMI a re-image
  // restores; gradiated-gpu-prod-host unless set.
  readonly launchTemplateName?: string;
  // The GPU account's key for bootstrap secrets.
  readonly secretKmsKeyId: string;
  readonly sessionName: string;
};

const roleArn = z
  .string()
  .regex(/^arn:aws:iam::(\d{12}):role\/[\w+=,.@/-]{1,512}$/);

export const awsAccountOf = (arn: string) => roleArn.parse(arn).split(":")[4]!;

export type Ec2Instance = {
  readonly id: string;
  readonly accountId: string;
  // pending, running, stopping, stopped, shutting-down or terminated.
  readonly state: string;
  readonly availabilityZone: string;
  readonly instanceType: string;
  readonly imageId: string;
  readonly launchTemplate?: { readonly id: string; readonly version: string };
  readonly launchedAt?: string;
  readonly tags: Readonly<Record<string, string>>;
  readonly instanceProfileArn?: string;
  // Attached EBS volumes, the root included; a re-image wipes only the root.
  readonly blockDevices?: number;
};

export type Ec2Gpus = {
  readonly count: number;
  // As EC2 names it, such as L4 or L40S.
  readonly name: string;
};

// The GPU instance families the fleet uses, so describing a host needs no
// ec2:DescribeInstanceTypes; any other type is looked up.
const FAMILIES: Record<
  string,
  { name: string; counts: Record<string, number> }
> = {
  g6: { name: "L4", counts: { "12xlarge": 4, "24xlarge": 4, "48xlarge": 8 } },
  gr6: { name: "L4", counts: {} },
  g6e: {
    name: "L40S",
    counts: { "12xlarge": 4, "24xlarge": 4, "48xlarge": 8 },
  },
};

export const knownGpus = (instanceType: string): Ec2Gpus | undefined => {
  const [family, size] = instanceType.split(".");
  const known = FAMILIES[family ?? ""];
  if (!known || !size || !/^\d*xlarge$/.test(size)) return undefined;
  return { count: known.counts[size] ?? 1, name: known.name };
};

// pending, in-progress, failing, succeeded, failed or failed-detached.
export type ReplaceRootVolumeTask = {
  readonly id: string;
  readonly state: string;
  // When EC2 started the task; listed tasks carry it.
  readonly started?: Date;
};

const TERMINAL_TASK_STATES = new Set([
  "succeeded",
  "failed",
  "failed-detached",
]);

// A task in any other state can still swap the root volume under a launcher.
export const replacementSettled = (task: ReplaceRootVolumeTask) =>
  TERMINAL_TASK_STATES.has(task.state);

export const isManaged = (instance: Ec2Instance) =>
  instance.tags[MANAGED_TAG.key] === MANAGED_TAG.value;

export const ec2InstanceArn = (
  region: string,
  accountId: string,
  instanceId: string,
) =>
  `arn:aws:ec2:${region}:${accountId}:instance/${ec2InstanceId.parse(instanceId)}`;

const named = (error: unknown, ...names: string[]) =>
  error instanceof Error && names.includes(error.name);

// How long writing a bootstrap secret waits for a forced deletion of the
// same name to finish; Secrets Manager completes one asynchronously.
export const SECRET_DELETION_WAIT_MS = 2 * 60_000;
const SECRET_DELETION_BACKOFF_MS = [1_000, 2_000, 5_000, 10_000];
const PROFILE_DETACH_WAIT_MS = 60_000;
const PROFILE_DETACH_POLL_MS = 2_000;

export const createAwsGpuClient = ({
  access,
  ec2,
  secrets,
  sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
  now = Date.now,
}: {
  readonly access: AwsGpuAccess;
  // Injected by tests; built from the assumed operator role otherwise.
  readonly ec2?: EC2Client;
  readonly secrets?: SecretsManagerClient;
  readonly sleep?: (ms: number) => Promise<void>;
  readonly now?: () => number;
}) => {
  const accountId = awsAccountOf(access.roleArn);
  const credentials =
    ec2 && secrets
      ? undefined
      : fromTemporaryCredentials({
          params: {
            RoleArn: access.roleArn,
            RoleSessionName: access.sessionName,
            DurationSeconds: 900,
          },
          clientConfig: { region: access.region },
        });
  const compute =
    ec2 ?? new EC2Client({ region: access.region, credentials: credentials! });
  const store =
    secrets ??
    new SecretsManagerClient({
      region: access.region,
      credentials: credentials!,
    });
  const id = (instanceId: string) => ec2InstanceId.parse(instanceId);
  const storage = new Map<string, boolean>();

  const instance = async (instanceId: string): Promise<Ec2Instance> => {
    const result = await compute.send(
      new DescribeInstancesCommand({ InstanceIds: [id(instanceId)] }),
    );
    const reservation = result.Reservations?.find((item) =>
      item.Instances?.some((found) => found.InstanceId === instanceId),
    );
    const found = reservation?.Instances?.find(
      (item) => item.InstanceId === instanceId,
    );
    if (!reservation || !found)
      throw new Error(`EC2 instance ${instanceId} was not found`);
    const tags = Object.fromEntries(
      (found.Tags ?? []).flatMap((tag) =>
        tag.Key === undefined ? [] : [[tag.Key, tag.Value ?? ""]],
      ),
    );
    const template = tags["aws:ec2launchtemplate:id"];
    const version = tags["aws:ec2launchtemplate:version"];
    return {
      id: instanceId,
      accountId: z
        .string()
        .regex(/^\d{12}$/)
        .parse(reservation.OwnerId),
      state: found.State?.Name ?? "unknown",
      availabilityZone: z
        .string()
        .min(1)
        .parse(found.Placement?.AvailabilityZone),
      instanceType: z.string().min(1).parse(found.InstanceType),
      imageId: found.ImageId ?? "",
      ...(template && version && { launchTemplate: { id: template, version } }),
      ...(found.LaunchTime && { launchedAt: found.LaunchTime.toISOString() }),
      tags,
      ...(found.IamInstanceProfile?.Arn && {
        instanceProfileArn: found.IamInstanceProfile.Arn,
      }),
      ...(found.BlockDeviceMappings?.length && {
        blockDevices: found.BlockDeviceMappings.length,
      }),
    };
  };

  const associations = async (instanceId: string) =>
    (
      await compute.send(
        new DescribeIamInstanceProfileAssociationsCommand({
          Filters: [
            { Name: "instance-id", Values: [id(instanceId)] },
            {
              Name: "state",
              Values: ["associating", "associated", "disassociating"],
            },
          ],
        }),
      )
    ).IamInstanceProfileAssociations ?? [];

  const isBootstrapProfile = (arn: string | undefined) =>
    arn?.endsWith(`/${access.bootstrapInstanceProfile}`) ?? false;

  return {
    accountId,
    region: access.region,

    instance,

    gpus: async (instanceType: string): Promise<Ec2Gpus> => {
      const known = knownGpus(instanceType);
      if (known) return known;
      const result = await compute.send(
        new DescribeInstanceTypesCommand({
          InstanceTypes: [instanceType as _InstanceType],
        }),
      );
      const type = result.InstanceTypes?.[0];
      const gpus = type?.GpuInfo?.Gpus ?? [];
      if (gpus.length !== 1 || !gpus[0]!.Count || !gpus[0]!.Name)
        throw new Error(
          `EC2 instance type ${instanceType} has no single kind of GPU`,
        );
      return { count: gpus[0]!.Count, name: gpus[0]!.Name };
    },

    // Instance-store volumes survive a root volume replacement, so whatever
    // was written to them outlives a re-image.
    instanceStorage: async (instanceType: string): Promise<boolean> => {
      const cached = storage.get(instanceType);
      if (cached !== undefined) return cached;
      const result = await compute.send(
        new DescribeInstanceTypesCommand({
          InstanceTypes: [instanceType as _InstanceType],
        }),
      );
      const type = result.InstanceTypes?.[0];
      if (!type)
        throw new Error(`EC2 instance type ${instanceType} was not found`);
      const supported =
        type.InstanceStorageSupported === true ||
        (type.InstanceStorageInfo?.TotalSizeInGB ?? 0) > 0;
      storage.set(instanceType, supported);
      return supported;
    },

    start: async (instanceId: string) => {
      await compute.send(
        new StartInstancesCommand({ InstanceIds: [id(instanceId)] }),
      );
    },

    // The AMI the launch template's default version pins. Existing hosts are
    // re-imaged onto it, so a pin change reaches them, not only new launches.
    launchTemplateImage: async (): Promise<string> => {
      const name = access.launchTemplateName ?? DEFAULT_LAUNCH_TEMPLATE;
      const result = await compute.send(
        new DescribeLaunchTemplateVersionsCommand({
          LaunchTemplateName: name,
          Versions: ["$Default"],
        }),
      );
      const versions = result.LaunchTemplateVersions ?? [];
      if (versions.length !== 1)
        throw new Error(`Launch template ${name} has no default version`);
      const image = amiId.safeParse(versions[0]!.LaunchTemplateData?.ImageId);
      if (!image.success)
        throw new Error(
          `The default version of launch template ${name} names no AMI`,
        );
      return image.data;
    },

    // Wipes the root volume and restores it from the given AMI, keeping the
    // instance, its ID and its capacity; the instance reboots and its launcher
    // runs again. Without an image, EC2 would restore the instance's original
    // launch AMI. The client token makes a repeated request one task.
    replaceRootVolume: async (
      instanceId: string,
      clientToken: string,
      imageId: string,
    ): Promise<ReplaceRootVolumeTask> => {
      const result = await compute.send(
        new CreateReplaceRootVolumeTaskCommand({
          InstanceId: id(instanceId),
          ImageId: amiId.parse(imageId),
          DeleteReplacedRootVolume: true,
          ClientToken: z
            .string()
            .regex(/^[\x21-\x7e]{1,64}$/)
            .parse(clientToken),
        }),
      );
      const task = result.ReplaceRootVolumeTask;
      return {
        id: z.string().min(1).parse(task?.ReplaceRootVolumeTaskId),
        state: task?.TaskState ?? "pending",
      };
    },

    replaceRootVolumeTask: async (
      instanceId: string,
      taskId: string,
    ): Promise<ReplaceRootVolumeTask> => {
      const result = await compute.send(
        new DescribeReplaceRootVolumeTasksCommand({
          ReplaceRootVolumeTaskIds: [taskId],
          Filters: [{ Name: "instance-id", Values: [id(instanceId)] }],
        }),
      );
      const task = result.ReplaceRootVolumeTasks?.[0];
      if (!task) throw new Error(`Replace-root-volume task ${taskId} is gone`);
      return { id: taskId, state: task.TaskState ?? "pending" };
    },

    // Every replace-root-volume task of the instance, oldest first, so a
    // caller can tell whether one is still in flight and how the last ended.
    replaceRootVolumeTasks: async (
      instanceId: string,
    ): Promise<ReplaceRootVolumeTask[]> => {
      const tasks: ReplaceRootVolumeTask[] = [];
      let nextToken: string | undefined;
      do {
        const result = await compute.send(
          new DescribeReplaceRootVolumeTasksCommand({
            Filters: [{ Name: "instance-id", Values: [id(instanceId)] }],
            MaxResults: 50,
            NextToken: nextToken,
          }),
        );
        for (const task of result.ReplaceRootVolumeTasks ?? []) {
          const started = task.StartTime ? new Date(task.StartTime) : undefined;
          tasks.push({
            id: z.string().min(1).parse(task.ReplaceRootVolumeTaskId),
            state: task.TaskState ?? "pending",
            ...(started && !Number.isNaN(started.getTime()) ? { started } : {}),
          });
        }
        nextToken = result.NextToken || undefined;
      } while (nextToken);
      return tasks.sort(
        (a, b) => (a.started?.getTime() ?? 0) - (b.started?.getTime() ?? 0),
      );
    },

    // A fresh instance has the bootstrap profile from its launch template;
    // enrollment removes it.
    bootstrapProfileAssociated: async (
      instanceId: string,
      { includeDetaching = false } = {},
    ) =>
      (await associations(instanceId)).some(
        (association) =>
          (includeDetaching || association.State !== "disassociating") &&
          isBootstrapProfile(association.IamInstanceProfile?.Arn),
      ),

    // Refuses an instance with any other profile: an instance has at most
    // one, and without the bootstrap profile a re-imaged launcher could never
    // read its secret. Callers run this before any destructive step.
    associateBootstrapProfile: async (instanceId: string) => {
      const current = await associations(instanceId);
      const other = current.find(
        (association) =>
          !isBootstrapProfile(association.IamInstanceProfile?.Arn),
      );
      if (other)
        throw new Error(
          `EC2 instance ${instanceId} has instance profile ${other.IamInstanceProfile?.Arn ?? other.AssociationId ?? "unknown"}, not ${access.bootstrapInstanceProfile}; remove it before re-imaging the instance`,
        );
      if (current.some((association) => association.State === "disassociating"))
        throw new Error(
          `EC2 instance ${instanceId} is still detaching its bootstrap instance profile`,
        );
      if (current.length) return false;

      await compute.send(
        new AssociateIamInstanceProfileCommand({
          InstanceId: id(instanceId),
          IamInstanceProfile: { Name: access.bootstrapInstanceProfile },
        }),
      );
      return true;
    },

    // Removes only the bootstrap profile, leaving the enrolled host with none
    // of its credentials; any other profile is not the fleet's to remove, and
    // is returned as kept.
    disassociateBootstrapProfile: async (instanceId: string) => {
      let current = await associations(instanceId);
      const isBootstrap = (association: (typeof current)[number]) =>
        isBootstrapProfile(association.IamInstanceProfile?.Arn);
      const bootstrap = current.filter(isBootstrap);

      for (const association of bootstrap) {
        if (association.State === "disassociating") continue;
        await compute.send(
          new DisassociateIamInstanceProfileCommand({
            AssociationId: association.AssociationId,
          }),
        );
      }

      const deadline = now() + PROFILE_DETACH_WAIT_MS;
      while (current.some(isBootstrap)) {
        if (now() + PROFILE_DETACH_POLL_MS > deadline)
          throw new Error(
            `EC2 instance ${instanceId} still has its bootstrap instance profile after waiting for detachment`,
          );

        await sleep(PROFILE_DETACH_POLL_MS);
        current = await associations(instanceId);
      }

      return {
        removed: bootstrap.length,
        kept: current.map(
          (association) =>
            association.IamInstanceProfile?.Arn ??
            association.AssociationId ??
            "unknown",
        ),
      };
    },

    // The operator can write and delete the secret but never read it back.
    // IAM lets a host read only the secret tagged with its own ARN.
    writeBootstrapSecret: async (
      instanceId: string,
      value: { image: string; tailscaleAuthKey: string },
    ) => {
      const name = bootstrapSecretName(instanceId);
      const secret = JSON.stringify({
        image: value.image,
        tailscale_auth_key: z
          .string()
          .startsWith("tskey-auth-")
          .parse(value.tailscaleAuthKey),
      });
      const create = () =>
        store.send(
          new CreateSecretCommand({
            Name: name,
            SecretString: secret,
            KmsKeyId: access.secretKmsKeyId,
            Tags: [
              {
                Key: "gradiated:instance-arn",
                Value: ec2InstanceArn(access.region, accountId, instanceId),
              },
              { Key: "Project", Value: "gradiated" },
              { Key: "Environment", Value: "prod" },
            ],
          }),
        );
      // A forced deletion of an earlier attempt's secret can still be in
      // progress; the name frees once it finishes. Such a secret is never
      // restored: its old key was single-use and the operator cannot read it.
      const deadline = now() + SECRET_DELETION_WAIT_MS;
      for (let attempt = 0; ; attempt++) {
        try {
          await create();
          return;
        } catch (error) {
          if (!named(error, "ResourceExistsException")) throw error;
        }
        let pendingDeletion: boolean;
        try {
          pendingDeletion =
            (await store.send(new DescribeSecretCommand({ SecretId: name })))
              .DeletedDate !== undefined;
        } catch (error) {
          // Deleted between the two calls; create it again.
          if (named(error, "ResourceNotFoundException") && now() < deadline)
            continue;
          throw error;
        }
        if (!pendingDeletion) {
          await store.send(
            new PutSecretValueCommand({ SecretId: name, SecretString: secret }),
          );
          return;
        }
        const wait =
          SECRET_DELETION_BACKOFF_MS[
            Math.min(attempt, SECRET_DELETION_BACKOFF_MS.length - 1)
          ]!;
        if (now() + wait > deadline)
          throw new Error(
            `Bootstrap secret ${name} is still being deleted; retry once its deletion finishes`,
          );
        await sleep(wait);
      }
    },

    // Forced, so a later re-image can create the same name once Secrets
    // Manager finishes the deletion, which it does asynchronously.
    deleteBootstrapSecret: async (instanceId: string) => {
      try {
        await store.send(
          new DeleteSecretCommand({
            SecretId: bootstrapSecretName(instanceId),
            ForceDeleteWithoutRecovery: true,
          }),
        );
        return true;
      } catch (error) {
        if (named(error, "ResourceNotFoundException")) return false;
        throw error;
      }
    },

    // A secret being deleted can no longer be read, though its name stays
    // taken until Secrets Manager finishes.
    bootstrapSecretReadable: async (instanceId: string) => {
      try {
        const secret = await store.send(
          new DescribeSecretCommand({
            SecretId: bootstrapSecretName(instanceId),
          }),
        );
        return secret.DeletedDate === undefined;
      } catch (error) {
        if (named(error, "ResourceNotFoundException")) return false;
        throw error;
      }
    },
  };
};

export type AwsGpuClient = ReturnType<typeof createAwsGpuClient>;
