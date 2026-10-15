import { createHash, randomBytes } from "node:crypto";

export const randomToken = (): string => randomBytes(32).toString("base64url");

export const sha256Digest = (secret: string): Buffer =>
  createHash("sha256").update(secret).digest();
