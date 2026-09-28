import {
  GetSecretValueCommand,
  SecretsManagerClient,
} from "@aws-sdk/client-secrets-manager";
import type { z } from "zod";

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
