import { ECRClient, GetAuthorizationTokenCommand } from "@aws-sdk/client-ecr";
import {
  GetSecretValueCommand,
  SecretsManagerClient,
} from "@aws-sdk/client-secrets-manager";
import type { z } from "zod";

import type { HostImage } from "./provider.js";

export const readSecret = async <Shape extends z.ZodType>(
  secretId: string,
  shape: Shape,
  client = new SecretsManagerClient({}),
): Promise<z.infer<Shape>> => {
  const { SecretString } = await client.send(
    new GetSecretValueCommand({ SecretId: secretId }),
  );

  return shape.parse(JSON.parse(SecretString ?? "null"));
};

const IMAGE = /^(?<registry>[a-z0-9.-]+)\/[a-z0-9._/-]+@sha256:[0-9a-f]{64}$/;
const ECR = /^\d{12}\.dkr\.ecr\.(?<region>[a-z0-9-]+)\.amazonaws\.com$/;

export const hostImage = async (
  reference: string,
  ecr = (region: string) => new ECRClient({ region }),
): Promise<HostImage> => {
  const registry = IMAGE.exec(reference)?.groups?.registry;
  if (!registry) {
    throw new Error(
      `${reference} must be pinned as registry/repository@sha256:<digest>`,
    );
  }

  const region = ECR.exec(registry)?.groups?.region;
  if (!region) return { reference, registry: null };

  const { authorizationData } = await ecr(region).send(
    new GetAuthorizationTokenCommand({}),
  );
  const token = authorizationData?.[0]?.authorizationToken;
  if (!token) throw new Error("ECR returned no authorization token");

  const [username, password] = Buffer.from(token, "base64")
    .toString()
    .split(":", 2);

  return { reference, registry: { username: username!, password: password! } };
};
