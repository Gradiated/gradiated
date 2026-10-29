import { randomBytes } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";
import {
  CreateSecretCommand,
  GetSecretValueCommand,
  SecretsManagerClient,
} from "@aws-sdk/client-secrets-manager";
import { GetObjectCommand, S3Client } from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";
import {
  bootstrapAuthKey,
  claimInstanceName,
  createRunPodClient,
  instanceTailnet,
  localStatus,
  releaseInstanceName,
  revokeAuthKey,
  socksConnector,
  sshRunner,
  tailscaleAuthKey,
  type OAuthCredentials,
} from "@gradiated/gpu-hosts";
import { z } from "zod";

import { createEnrollment, type EnrollmentDependencies } from "./enroll.js";
import type { GpuHost } from "./hosts.js";
import type { Pins } from "./pins.js";

const PLATFORM = "gradiated/prod/platform";

export type EnrollmentSettings = {
  hostKeysDirectory: string;
  apiEndpoint: string;
  socksPort: number;
  localApiSocket: string;
};

const secrets = new SecretsManagerClient({});

const readSecret = async (id: string) => {
  try {
    return (await secrets.send(new GetSecretValueCommand({ SecretId: id })))
      .SecretString;
  } catch (error) {
    if ((error as Error).name === "ResourceNotFoundException") return undefined;
    throw error;
  }
};

const oauth =
  (name: string): OAuthCredentials =>
  async () =>
    z
      .object({
        client_id: z.string().min(1),
        client_secret: z.string().min(1),
      })
      .parse(JSON.parse((await readSecret(`${PLATFORM}/${name}`)) ?? "null"));

const runPodKey = async () =>
  z
    .object({ "runpod-api-key": z.string().min(1) })
    .safeParse(JSON.parse((await readSecret(`${PLATFORM}/gpu-fleet`)) ?? "{}"))
    .data?.["runpod-api-key"];

export const productionRunPod = async () => {
  const apiKey = await runPodKey();
  return apiKey
    ? createRunPodClient({ apiKey, userAgent: "gradiated-gpu-fleet" })
    : undefined;
};

// Management keys of enrolled hosts are mounted; a new host's key is created
// in Secrets Manager at the path its GpuHost names.
const managementKey =
  (directory: string) =>
  async (host: GpuHost): Promise<string> => {
    const id = host.spec.instanceId;
    try {
      return (await readFile(path.join(directory, id), "utf8")).trim();
    } catch {
      /* Not mounted yet: read or create it below. */
    }

    const { key, property } = host.spec.managementSecret;
    const stored = await readSecret(key);
    const value = property
      ? (JSON.parse(stored ?? "{}") as Record<string, unknown>)[property]
      : stored;
    if (typeof value === "string" && value.length >= 32) return value;
    if (key !== `${PLATFORM}/gpu-host/${id}` || stored !== undefined)
      throw new Error(`The management key ${key} is missing or invalid`);

    const created = randomBytes(48).toString("base64url");
    try {
      await secrets.send(
        new CreateSecretCommand({
          Name: key,
          SecretString: created,
          Tags: [
            { Key: "Project", Value: "gradiated" },
            { Key: "Environment", Value: "prod" },
          ],
        }),
      );
      return created;
    } catch (error) {
      if ((error as Error).name !== "ResourceExistsException") throw error;
      return z
        .string()
        .min(32)
        .parse(await readSecret(key));
    }
  };

const bundleUrl = (pins: () => Promise<Pins>) => async (sha256: string) => {
  const account = (await pins()).image.match(/^(\d{12})\.dkr\.ecr\./)?.[1];
  if (!account) throw new Error("The pinned image names no artifact account");

  return getSignedUrl(
    new S3Client({ region: "us-east-1" }),
    new GetObjectCommand({
      Bucket: `gradiated-prod-model-artifacts-${account}`,
      Key: `bundles/sha256/${sha256}.tar.gz`,
    }),
    { expiresIn: 3600 },
  );
};

export const productionEnrollment = (
  settings: EnrollmentSettings,
  runpod: EnrollmentDependencies["runpod"],
  pins: () => Promise<Pins>,
) => {
  const enrollment = oauth("tailscale-gpu-enrollment");
  const bootstrap = oauth("tailscale-gpu-bootstrap");
  return createEnrollment({
    runpod,
    tailnet: {
      status: () => localStatus(settings.localApiSocket),
      run: sshRunner(socksConnector("127.0.0.1", settings.socksPort)),
    },
    instanceTailnet: (instanceId) =>
      instanceTailnet(instanceId, fetch, enrollment),
    bootstrapKey: (podId) => bootstrapAuthKey(podId, fetch, bootstrap),
    inferenceKey: (instanceId) =>
      tailscaleAuthKey(instanceId, fetch, enrollment),
    revokeKey: (client, id) =>
      revokeAuthKey(id, fetch, client === "bootstrap" ? bootstrap : enrollment),
    releaseName: (instanceId) =>
      releaseInstanceName(instanceId, fetch, enrollment),
    claimName: (instanceId, since) =>
      claimInstanceName(instanceId, since, fetch, enrollment),
    managementKey: managementKey(settings.hostKeysDirectory),
    bundleUrl: bundleUrl(pins),
    apiEndpoint: settings.apiEndpoint,
  });
};
