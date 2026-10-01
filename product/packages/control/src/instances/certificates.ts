import { createHash, randomBytes } from "node:crypto";
import { z } from "zod";

import { createInstanceCertificateStore } from "./certificate-store.js";
import type { ControlDatabase } from "../db/client.js";

const tokenSchema = z.string().regex(/^[A-Za-z0-9_-]{43}$/);
const tokenHash = (token: string) =>
  createHash("sha256").update(tokenSchema.parse(token)).digest("hex");

export const createInstanceCertificateService = (database: ControlDatabase) => {
  const store = createInstanceCertificateStore(database);

  return {
    async enroll(instanceId: string, nomadNodeId: string) {
      const token = randomBytes(32).toString("base64url");
      await store.enroll({
        instanceId,
        nomadNodeId,
        tokenHash: tokenHash(token),
      });

      return token;
    },
    revoke: store.revoke,
    observations: store.observations,
    observe: (
      instanceId: string,
      nomadNodeId: string,
      token: string,
      expiresAt: Date,
      renewalDueAt: Date,
    ) =>
      store.observe(
        { instanceId, nomadNodeId, tokenHash: tokenHash(token) },
        expiresAt,
        renewalDueAt,
      ),
    issue: <T>(
      instanceId: string,
      nomadNodeId: string,
      token: string,
      issue: () => Promise<T>,
    ) =>
      store.issue(
        { instanceId, nomadNodeId, tokenHash: tokenHash(token) },
        issue,
      ),
  };
};

export type InstanceCertificateService = ReturnType<
  typeof createInstanceCertificateService
>;
export {
  CertificateAuthorizationError,
  CertificateRateLimitError,
} from "./certificate-store.js";
