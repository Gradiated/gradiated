import { z } from "zod";

const EnvironmentSchema = z
  .object({
    AUTH_EMAIL_FROM: z.string().trim().min(1).optional(),
    AUTH_TEST_MODE: z
      .enum(["true", "false"])
      .default("false")
      .transform((value) => value === "true"),
    BETTER_AUTH_SECRET: z.string().min(32),
    BETTER_AUTH_URL: z.url(),
    DATABASE_URL: z.url(),
    HOST: z.string().min(1).default("0.0.0.0"),
    NODE_ENV: z
      .enum(["development", "test", "production"])
      .default("development"),
    PORT: z.coerce.number().int().min(1).max(65_535).default(3001),
    CONSOLE_URL: z.url().default("http://localhost:3000"),
    GITHUB_CLIENT_ID: z.string().trim().min(1).optional(),
    GITHUB_CLIENT_SECRET: z.string().trim().min(1).optional(),
    GOOGLE_CLIENT_ID: z.string().trim().min(1).optional(),
    GOOGLE_CLIENT_SECRET: z.string().trim().min(1).optional(),
    RESEND_API_KEY: z.string().trim().min(1).optional(),
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
      Boolean(value.GITHUB_CLIENT_ID) === Boolean(value.GITHUB_CLIENT_SECRET),
    {
      message:
        "GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET must be configured together.",
    },
  )
  .refine(
    (value) =>
      Boolean(value.GOOGLE_CLIENT_ID) === Boolean(value.GOOGLE_CLIENT_SECRET),
    {
      message:
        "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be configured together.",
    },
  )
  .refine((value) => value.NODE_ENV !== "production" || !value.AUTH_TEST_MODE, {
    message: "AUTH_TEST_MODE cannot be enabled in production.",
    path: ["AUTH_TEST_MODE"],
  })
  .refine(
    (value) =>
      value.AUTH_TEST_MODE ||
      Boolean(value.AUTH_EMAIL_FROM && value.RESEND_API_KEY),
    {
      message:
        "AUTH_EMAIL_FROM and RESEND_API_KEY are required when AUTH_TEST_MODE is disabled.",
    },
  )
  .refine(
    (value) =>
      value.NODE_ENV !== "production" || Boolean(value.GITHUB_CLIENT_ID),
    {
      message: "GitHub authentication credentials are required in production.",
    },
  )
  .refine(
    (value) =>
      value.NODE_ENV !== "production" || Boolean(value.GOOGLE_CLIENT_ID),
    {
      message: "Google authentication credentials are required in production.",
    },
  )
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
