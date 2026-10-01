import { and, eq, isNull, isNotNull } from "drizzle-orm";
import { z } from "zod";

import type { ControlDatabase } from "../db/client.js";
import { instances } from "../db/schema/instances.js";
import {
  instanceCertificateSchema,
  type InstanceCertificate,
} from "./certificate-schema.js";

const identitySchema = z.strictObject({
  instanceId: z.uuid(),
  nomadNodeId: z.uuid(),
  tokenHash: z.string().regex(/^[a-f0-9]{64}$/),
});
const recordSchema = z.object({
  id: z.uuid(),
  nomadNodeId: z.uuid().nullable(),
  certificate: instanceCertificateSchema.nullable(),
});
const columns = {
  id: instances.id,
  nomadNodeId: instances.nomadNodeId,
  certificate: instances.certificate,
};

export class CertificateAuthorizationError extends Error {}
export class CertificateRateLimitError extends Error {}

const lockedCredential = async (
  transaction: Pick<ControlDatabase, "select">,
  input: z.infer<typeof identitySchema>,
) => {
  const [record] = await transaction
    .select(columns)
    .from(instances)
    .where(and(eq(instances.id, input.instanceId), isNull(instances.retiredAt)))
    .for("update");
  if (!record) throw new CertificateAuthorizationError("Unauthorized host");

  const parsed = recordSchema.parse(record);
  const certificate = parsed.certificate;
  if (
    !certificate ||
    certificate.revokedAt ||
    parsed.nomadNodeId !== input.nomadNodeId ||
    certificate.nomadNodeId !== input.nomadNodeId ||
    certificate.tokenHash !== input.tokenHash
  ) {
    throw new CertificateAuthorizationError("Unauthorized host");
  }

  return certificate;
};

const writeCertificate = async (
  database: Pick<ControlDatabase, "update">,
  instanceId: string,
  value: InstanceCertificate,
) => {
  const certificate = instanceCertificateSchema.parse(value);
  await database
    .update(instances)
    .set({ certificate })
    .where(eq(instances.id, instanceId));
};

export const createInstanceCertificateStore = (database: ControlDatabase) => ({
  async enroll(value: z.infer<typeof identitySchema>) {
    const { instanceId, ...identity } = identitySchema.parse(value);
    const certificate = instanceCertificateSchema.parse({
      ...identity,
      revokedAt: null,
      issuedAt: null,
      expiresAt: null,
      observedAt: null,
      renewalDueAt: null,
    });
    const [record] = await database
      .update(instances)
      .set({ certificate })
      .where(and(eq(instances.id, instanceId), isNull(instances.retiredAt)))
      .returning(columns);
    if (!record) throw new CertificateAuthorizationError("Unauthorized host");

    return recordSchema.parse(record).certificate!;
  },

  async revoke(instanceId: string) {
    const id = z.uuid().parse(instanceId);
    await database.transaction(async (transaction) => {
      const [record] = await transaction
        .select(columns)
        .from(instances)
        .where(eq(instances.id, id))
        .for("update");
      if (!record) return;

      const { certificate } = recordSchema.parse(record);
      if (certificate)
        await writeCertificate(transaction, id, {
          ...certificate,
          revokedAt: new Date().toISOString(),
        });
    });
  },

  async observe(
    value: z.infer<typeof identitySchema>,
    expiresAt: Date,
    renewalDueAt: Date,
  ) {
    const input = identitySchema.parse(value);
    const expiry = z.date().parse(expiresAt).toISOString();
    const due = z.date().parse(renewalDueAt).toISOString();
    await database.transaction(async (transaction) => {
      const certificate = await lockedCredential(transaction, input);
      await writeCertificate(transaction, input.instanceId, {
        ...certificate,
        observedAt: new Date().toISOString(),
        expiresAt: expiry,
        renewalDueAt: due,
      });
    });
  },

  async observations() {
    const records = await database
      .select(columns)
      .from(instances)
      .where(
        and(isNull(instances.retiredAt), isNotNull(instances.nomadNodeId)),
      );

    return records.flatMap((value) => {
      const record = recordSchema.parse(value);
      const certificate =
        record.certificate?.nomadNodeId === record.nomadNodeId
          ? record.certificate
          : null;
      if (certificate?.revokedAt) return [];

      return [
        {
          instanceId: record.id,
          observedExpiresAt: certificate?.expiresAt
            ? new Date(certificate.expiresAt)
            : null,
          observedAt: certificate?.observedAt
            ? new Date(certificate.observedAt)
            : null,
          observedRenewalDueAt: certificate?.renewalDueAt
            ? new Date(certificate.renewalDueAt)
            : null,
        },
      ];
    });
  },

  async issue<T>(
    value: z.infer<typeof identitySchema>,
    issue: () => Promise<T>,
  ): Promise<T> {
    const input = identitySchema.parse(value);
    return database.transaction(async (transaction) => {
      const certificate = await lockedCredential(transaction, input);
      if (
        certificate.issuedAt &&
        Date.now() - Date.parse(certificate.issuedAt) < 60_000
      ) {
        throw new CertificateRateLimitError("Try again in one minute");
      }

      const result = await issue();
      await writeCertificate(transaction, input.instanceId, {
        ...certificate,
        issuedAt: new Date().toISOString(),
      });

      return result;
    });
  },
});
