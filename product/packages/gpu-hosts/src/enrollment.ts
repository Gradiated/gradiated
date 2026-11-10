import { z } from "zod";

import type { RunSsh, SshTarget } from "./ssh.js";

const tailnetAddress = z
  .string()
  .regex(
    /^100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])\.(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9]?[0-9])$/,
  );

// What `gradiated-host enroll` reads on stdin. The GPU base image validates it
// against enrollment-payload.schema.json, which a test keeps equal to this.
export const enrollmentPayloadSchema = z.strictObject({
  version: z.literal(1),
  instance_id: z
    .string()
    .regex(/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/),
  management_token: z.string().regex(/^[A-Za-z0-9_-]{32,128}$/),
  // Tailscale's auth keys, or headscale's in the end-to-end test.
  auth_key: z.string().regex(/^(?:tskey|hskey)-auth-[A-Za-z0-9_-]{1,200}$/),
  api_endpoint: tailnetAddress,
  host_bundle: z.strictObject({
    sha256: z.string().regex(/^[0-9a-f]{64}$/),
    base_id: z.string().regex(/^[A-Za-z0-9._-]{1,64}$/),
    url: z.string().regex(/^https:\/\/[^\s]{1,4096}$/),
  }),
});

// What `gradiated-host enroll` prints on stdout.
export const enrollmentResultSchema = z.strictObject({
  version: z.literal(1),
  tailscale_ip: tailnetAddress,
  gpu_count: z.int().min(1).max(8),
  gpu_product: z.enum(["B200", "B300", "H100", "H200", "L40S", "RTX-PRO-6000"]),
  cpu: z.int().min(1).max(512),
  memory_gib: z.int().min(1).max(4096),
  promotion: z.boolean(),
});

export type EnrollmentPayload = z.infer<typeof enrollmentPayloadSchema>;
export type EnrollmentResult = z.infer<typeof enrollmentResultSchema>;

export const enrollmentPayload = (
  instance: { readonly sku: string },
  fields: Omit<EnrollmentPayload, "version">,
): EnrollmentPayload => {
  if (!/^\d+x .*\b(B200|B300|H100|H200|L40S|RTX PRO 6000)\b/.test(instance.sku))
    throw new Error(
      "GPU enrollment supports B200, B300, H100, H200, L40S and RTX PRO 6000 hosts",
    );
  return enrollmentPayloadSchema.parse({ version: 1, ...fields });
};

// Credentials travel on stdin only; the command line is the same for every host.
export const ENROLL_COMMAND = "/usr/local/bin/gradiated-host enroll";

export const enroll = async (
  run: RunSsh,
  target: SshTarget,
  payload: EnrollmentPayload,
): Promise<EnrollmentResult> => {
  const output = await run(
    target,
    ENROLL_COMMAND,
    JSON.stringify(enrollmentPayloadSchema.parse(payload)),
    30 * 60 * 1000,
  );
  try {
    return enrollmentResultSchema.parse(JSON.parse(output));
  } catch {
    throw new Error("gradiated-host enroll returned an invalid result");
  }
};
