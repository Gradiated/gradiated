import { createHash, randomBytes } from "node:crypto";

export const generateApiKeySecret = (): string =>
  `grad_${randomBytes(32).toString("base64url")}`;

// The gateway authenticates a key by this same SHA-256 digest of the secret.
export const apiKeyDigest = (secret: string): Buffer =>
  createHash("sha256").update(secret).digest();
