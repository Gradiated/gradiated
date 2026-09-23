import { execFile } from "node:child_process";
import { promisify } from "node:util";

import { z } from "@hono/zod-openapi";

import type { HostImage } from "./provider.js";

const execute = promisify(execFile);

const aws = async (...args: string[]) =>
  (await execute("aws", args, { maxBuffer: 1024 * 1024 })).stdout.trim();

export const readSecret = async <Shape extends z.ZodType>(
  secretId: string,
  shape: Shape,
): Promise<z.infer<Shape>> =>
  shape.parse(
    JSON.parse(
      await aws(
        "secretsmanager",
        "get-secret-value",
        "--secret-id",
        secretId,
        "--query",
        "SecretString",
        "--output",
        "text",
      ),
    ),
  );

const IMAGE = /^(?<registry>[a-z0-9.-]+)\/[a-z0-9._/-]+@sha256:[0-9a-f]{64}$/;
const ECR = /^\d{12}\.dkr\.ecr\.(?<region>[a-z0-9-]+)\.amazonaws\.com$/;

export const hostImage = async (reference: string): Promise<HostImage> => {
  const registry = IMAGE.exec(reference)?.groups?.registry;
  if (!registry) {
    throw new Error(
      `${reference} must be pinned as registry/repository@sha256:<digest>`,
    );
  }
  const region = ECR.exec(registry)?.groups?.region;
  if (!region) return { reference, registry: null };

  return {
    reference,
    registry: {
      username: "AWS",
      password: await aws("ecr", "get-login-password", "--region", region),
    },
  };
};
