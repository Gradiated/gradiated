import { readFile } from "node:fs/promises";
import path from "node:path";
import { randomBytes } from "node:crypto";
import {
  CreateSecretCommand,
  GetSecretValueCommand,
  SecretsManagerClient,
} from "@aws-sdk/client-secrets-manager";
import { GetObjectCommand, S3Client } from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";

import {
  createControlDatabase,
  createInstanceService,
} from "@gradiated/control";
import { z } from "zod";

import { createAwsProvider } from "./ec2.js";
import { createRegistrations } from "./registration.js";
import { createRunPodProvider } from "./runpod.js";
import {
  bootstrapAuthKey,
  claimInstanceName,
  createAwsGpuClient,
  enrollmentPayload,
  instanceHasDevice,
  localStatus,
  releaseInstanceName,
  socksConnector,
  sshRunner,
  tailscaleAuthKey,
} from "@gradiated/gpu-hosts";

import { readSecret } from "./aws.js";
import { artifactAccount } from "./image.js";

export type RegistrationSettings = {
  readonly credentialsDirectory: string;
  readonly hostImage: string;
  readonly apiEndpoint: string;
  readonly hostBundleSha256?: string;
  readonly hostBundleBaseId?: string;
  readonly tailnet: {
    readonly socksPort: number;
    readonly localApiSocket: string;
  };
  // The GPU account's operator role; AWS registration is off without it.
  readonly aws?: {
    readonly region: string;
    readonly roleArn: string;
    readonly bootstrapInstanceProfile: string;
    readonly launchTemplateName: string;
    readonly secretKmsKeyId: string;
    // The GPU base image AWS hosts run, by tag or digest; hostImage unless
    // set. Every image must still enroll from the one pinned host bundle and
    // its base ID.
    readonly hostImage?: string;
  };
};

const oauthCredentials = (secret: string) => () =>
  readSecret(
    secret,
    z.object({
      client_id: z.string().min(1),
      client_secret: z.string().min(1),
    }),
  );
const enrollmentCredentials = oauthCredentials(
  "gradiated/prod/platform/tailscale-gpu-enrollment",
);
// Its OAuth client can only issue tag:gpu-bootstrap keys, which have no
// network grants: only administrators and ops-mcp reach such a pod, over
// Tailscale SSH.
const bootstrapCredentials = oauthCredentials(
  "gradiated/prod/platform/tailscale-gpu-bootstrap",
);

export const productionRegistrations = (
  settings: RegistrationSettings,
  audit: (event: Record<string, unknown>) => void,
) => {
  const credential = async (name: string) => {
    try {
      return (
        await readFile(path.join(settings.credentialsDirectory, name), "utf8")
      ).trim();
    } catch {
      throw new Error(`Registration is not configured: ${name} is missing`);
    }
  };

  const tailnet = () => ({
    run: sshRunner(socksConnector("127.0.0.1", settings.tailnet.socksPort)),
    status: () => localStatus(settings.tailnet.localApiSocket),
    releaseName: (instanceId: string) =>
      releaseInstanceName(instanceId, fetch, enrollmentCredentials),
    claimName: (instanceId: string, since: Date) =>
      claimInstanceName(instanceId, since, fetch, enrollmentCredentials),
    hasDevice: (instanceId: string) =>
      instanceHasDevice(instanceId, fetch, enrollmentCredentials),
  });
  // One single-use tag:gpu-bootstrap key per RunPod pod or EC2 instance.
  const bootstrapKey = (providerInstanceId: string) =>
    bootstrapAuthKey(providerInstanceId, fetch, bootstrapCredentials);

  let instances: ReturnType<typeof createInstanceService> | undefined;
  return createRegistrations({
    providers: {
      runpod: async () =>
        createRunPodProvider({
          apiKey: await credential("runpod-api-key"),
          bootstrapKey,
          audit,
          tailnet: tailnet(),
        }),
      aws: async () => {
        if (!settings.aws)
          throw new Error(
            "Registration is not configured: AWS_GPU_OPERATOR_ROLE_ARN is unset",
          );
        return createAwsProvider({
          client: createAwsGpuClient({
            access: { ...settings.aws, sessionName: "gradiated-ops-mcp" },
          }),
          bootstrapKey,
          audit,
          tailnet: tailnet(),
        });
      },
    },
    instances: async () =>
      (instances ??= createInstanceService(
        createControlDatabase(await credential("database-url"), 2).database,
      )),
    hostImage: settings.hostImage,
    ...(settings.aws?.hostImage && {
      hostImages: { aws: settings.aws.hostImage },
    }),
    // Every gpu-base image enrolls from a pinned host bundle.
    enrollmentPayload: async (instance, id, key, auth) => {
      const digest = z
        .string()
        .regex(/^[0-9a-f]{64}$/)
        .parse(settings.hostBundleSha256);
      // The bundle lives beside the image this instance's provider runs.
      const account = artifactAccount(
        (instance.provider === "aws" && settings.aws?.hostImage) ||
          settings.hostImage,
      );

      // The pinned bundle must be built for the image that runs gradiated-host enroll.
      const baseId = (
        await readFile(
          new URL(
            "../../../../inference/images/gpu-base/base-id",
            import.meta.url,
          ),
          "utf8",
        )
      ).trim();
      if (settings.hostBundleBaseId !== baseId)
        throw new Error(
          `GPU_HOST_BOOTSTRAP_BASE_ID is ${settings.hostBundleBaseId ?? "unset"}, but enrollment needs a host bundle for base ${baseId}`,
        );

      return enrollmentPayload(instance, {
        instance_id: id,
        management_token: key,
        auth_key: auth,
        api_endpoint: settings.apiEndpoint,
        host_bundle: {
          sha256: digest,
          base_id: baseId,
          url: await getSignedUrl(
            new S3Client({ region: "us-east-1" }),
            new GetObjectCommand({
              Bucket: `gradiated-prod-model-artifacts-${account}`,
              Key: `bundles/sha256/${digest}.tar.gz`,
            }),
            { expiresIn: 3600 },
          ),
        },
      });
    },
    managementKey: async (id) => {
      const client = new SecretsManagerClient({});
      const existing = "gradiated/prod/platform/gpu-controller";
      let fleet: Record<string, string>;
      try {
        fleet = JSON.parse(
          (await client.send(new GetSecretValueCommand({ SecretId: existing })))
            .SecretString ?? "{}",
        );
      } catch {
        throw new Error(
          "GPU management key inventory is unavailable or invalid",
        );
      }
      if (typeof fleet[id] === "string")
        return { key: fleet[id], secretId: existing, property: id };
      const secretId = `gradiated/prod/platform/gpu-host/${z.uuid().parse(id)}`;
      try {
        const result = await client.send(
          new GetSecretValueCommand({ SecretId: secretId }),
        );
        return { key: z.string().min(32).parse(result.SecretString), secretId };
      } catch (error) {
        if (
          !(error instanceof Error) ||
          error.name !== "ResourceNotFoundException"
        )
          throw error;
      }
      const key = randomBytes(48).toString("base64url");
      try {
        await client.send(
          new CreateSecretCommand({
            Name: secretId,
            SecretString: key,
            Tags: [
              { Key: "Project", Value: "gradiated" },
              { Key: "Environment", Value: "prod" },
            ],
          }),
        );
        return { key, secretId };
      } catch (error) {
        if (
          !(error instanceof Error) ||
          error.name !== "ResourceExistsException"
        )
          throw error;
        return {
          key: z
            .string()
            .min(32)
            .parse(
              (
                await client.send(
                  new GetSecretValueCommand({ SecretId: secretId }),
                )
              ).SecretString,
            ),
          secretId,
        };
      }
    },
    tailscaleAuthKey: (instanceId) =>
      tailscaleAuthKey(instanceId, fetch, enrollmentCredentials),
    audit,
  });
};
