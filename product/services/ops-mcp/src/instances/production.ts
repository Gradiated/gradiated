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
import { hostBootstrapEnvironment } from "./host-bootstrap.js";

import {
  createControlDatabase,
  createInstanceService,
} from "@gradiated/control";
import { z } from "zod";

import { createRegistrations } from "./registration.js";
import { createRunPodProvider } from "./runpod.js";
import { sshRunner } from "./ssh.js";
import { tailscaleAuthKey } from "./tailscale.js";

export type RegistrationSettings = {
  readonly credentialsDirectory: string;
  readonly hostImage: string;
  readonly apiEndpoint: string;
  readonly hostBundleSha256?: string;
};

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

  let instances: ReturnType<typeof createInstanceService> | undefined;
  return createRegistrations({
    providers: {
      runpod: async () => {
        const optional = async (name: string) =>
          readFile(
            path.join(settings.credentialsDirectory, name),
            "utf8",
          ).catch((error: NodeJS.ErrnoException) => {
            if (error.code === "ENOENT") return null;

            throw new Error(
              `Cannot read in-place enrollment credential ${name}`,
            );
          });
        const [privateKey, pinnedKeys] = await Promise.all([
          optional("runpod-ssh-key"),
          optional("runpod-ssh-host-keys"),
        ]);
        let inPlace;
        if (privateKey && pinnedKeys) {
          let parsed: unknown;
          try {
            parsed = JSON.parse(pinnedKeys);
          } catch {
            throw new Error("runpod-ssh-host-keys is not valid JSON");
          }
          const hostKeys = z
            .record(z.string(), z.string().regex(/^[a-f0-9]{64}$/))
            .parse(parsed);
          inPlace = { run: sshRunner(privateKey), hostKeys };
        }

        return createRunPodProvider({
          apiKey: await credential("runpod-api-key"),
          inPlace,
        });
      },
    },
    instances: async () =>
      (instances ??= createInstanceService(
        createControlDatabase(await credential("database-url"), 2).database,
      )),
    hostImage: settings.hostImage,
    bootstrap: async (instance, id, key, auth) => {
      let hostBundle;
      if (settings.hostBundleSha256) {
        const digest = z
          .string()
          .regex(/^[0-9a-f]{64}$/)
          .parse(settings.hostBundleSha256);
        const account = settings.hostImage.match(/^(\d{12})\.dkr\.ecr\./)?.[1];
        if (!account)
          throw new Error("GPU base image must identify its artifact account");

        hostBundle = {
          sha256: digest,
          base_id: (
            await readFile(
              new URL(
                "../../../../inference/images/gpu-base/base-id",
                import.meta.url,
              ),
              "utf8",
            )
          ).trim(),
          url: await getSignedUrl(
            new S3Client({ region: "us-east-1" }),
            new GetObjectCommand({
              Bucket: `gradiated-prod-model-artifacts-${account}`,
              Key: `bundles/sha256/${digest}.tar.gz`,
            }),
            { expiresIn: 3600 },
          ),
        };
      }

      return hostBootstrapEnvironment(
        instance,
        id,
        key,
        auth,
        settings.apiEndpoint,
        hostBundle,
      );
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
    tailscaleAuthKey,
    audit,
  });
};
