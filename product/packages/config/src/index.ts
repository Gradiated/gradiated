import { z } from "zod";

const EnvironmentSchema = z
  .object({
    BETTER_AUTH_SECRET: z.string().min(32),
    BETTER_AUTH_MIN_PASSWORD_LENGTH: z.coerce
      .number()
      .int()
      .min(4)
      .max(128)
      .default(12),
    BETTER_AUTH_URL: z.url(),
    DATABASE_URL: z.url(),
    HOST: z.string().min(1).default("0.0.0.0"),
    NODE_ENV: z
      .enum(["development", "test", "production"])
      .default("development"),
    PORT: z.coerce.number().int().min(1).max(65_535).default(3001),
    CONSOLE_URL: z.url().default("http://localhost:3000"),
    STRIPE_SECRET_KEY: z.string().min(1).optional(),
    STRIPE_WEBHOOK_SECRET: z.string().min(1).optional(),
    TRUSTED_ORIGINS: z
      .string()
      .default("http://localhost:3000,http://127.0.0.1:3000")
      .transform((value) => value.split(",").map((origin) => origin.trim()))
      .pipe(z.array(z.url()).min(1)),
    VALKEY_IAM_CACHE_NAME: z.string().min(1).optional(),
    VALKEY_IAM_REGION: z.string().min(1).optional(),
    VALKEY_IAM_USER: z.string().min(1).optional(),
    VALKEY_URL: z.url(),
  })
  .refine(
    (value) =>
      Boolean(value.STRIPE_SECRET_KEY) === Boolean(value.STRIPE_WEBHOOK_SECRET),
    {
      message:
        "STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET must be configured together.",
    },
  )
  .refine(
    (value) => {
      const iamValues = [
        value.VALKEY_IAM_CACHE_NAME,
        value.VALKEY_IAM_REGION,
        value.VALKEY_IAM_USER,
      ];
      return iamValues.every(Boolean) || iamValues.every((item) => !item);
    },
    {
      message:
        "VALKEY_IAM_CACHE_NAME, VALKEY_IAM_REGION and VALKEY_IAM_USER must be configured together.",
    },
  )
  .readonly();

export type Environment = z.infer<typeof EnvironmentSchema>;

export const parseEnvironment = (environment: NodeJS.ProcessEnv): Environment =>
  EnvironmentSchema.parse(environment);
