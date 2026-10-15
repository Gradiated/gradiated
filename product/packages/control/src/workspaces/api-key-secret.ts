import { randomToken, sha256Digest } from "../secrets.js";

export const generateApiKeySecret = (): string => `grad_${randomToken()}`;

// The gateway authenticates a key by this same SHA-256 digest of the secret.
export const apiKeyDigest = sha256Digest;
