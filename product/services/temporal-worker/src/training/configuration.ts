import { z } from "zod";

const schema = z
  .object({
    TRAINING_POD_IDS: z
      .string()
      .transform((value) => value.split(","))
      .pipe(
        z
          .array(z.string().regex(/^[a-z0-9]+$/))
          .min(1)
          .max(4)
          .refine((ids) => new Set(ids).size === ids.length),
      ),
    TRAINING_BUNDLE_URL: z
      .string()
      .regex(
        /^s3::https:\/\/[a-z0-9.-]+\.s3\.us-east-1\.amazonaws\.com\/bundles\/sha256\/[0-9a-f]{64}\.tar\.gz$/,
      ),
    TRAINING_BUNDLE_SHA256: z.string().regex(/^[0-9a-f]{64}$/),
    TRAINING_BASE_ID: z.string().min(1),
    TRAINING_GPU_MODEL: z.string().min(1).default("H100"),
    TRAINING_HOST_TOKEN: z.string().min(32),
    TRAINING_ARTIFACTS_BUCKET: z.string().min(1),
  })
  .refine(
    (value) =>
      value.TRAINING_BUNDLE_URL.endsWith(
        `${value.TRAINING_BUNDLE_SHA256}.tar.gz`,
      ),
    { message: "Training bundle URL and SHA-256 must match" },
  );
export const trainingConfiguration = (environment: NodeJS.ProcessEnv) =>
  schema.parse(environment);
