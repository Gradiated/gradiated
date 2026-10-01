import { z } from "zod";

export const instanceCertificateSchema = z.strictObject({
  nomadNodeId: z.uuid(),
  tokenHash: z.string().regex(/^[a-f0-9]{64}$/),
  revokedAt: z.iso.datetime().nullable(),
  issuedAt: z.iso.datetime().nullable(),
  expiresAt: z.iso.datetime().nullable(),
  observedAt: z.iso.datetime().nullable(),
  renewalDueAt: z.iso.datetime().nullable(),
});

export type InstanceCertificate = z.infer<typeof instanceCertificateSchema>;
