import { z } from "zod";

const EnvironmentFieldsSchema = z.object({
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
  STRIPE_PUBLISHABLE_KEY: z.string().min(1).optional(),
  TRUSTED_ORIGINS: z
    .string()
    .default("http://localhost:3000,http://127.0.0.1:3000")
    .transform((value) => value.split(",").map((origin) => origin.trim()))
    .pipe(z.array(z.url()).min(1)),
  VALKEY_IAM_CACHE_NAME: z.string().trim().min(1).optional(),
  VALKEY_IAM_REGION: z.string().trim().min(1).optional(),
  VALKEY_IAM_USER: z.string().trim().min(1).optional(),
  VALKEY_URL: z.url(),
});

type EnvironmentFields = z.infer<typeof EnvironmentFieldsSchema>;
type EnvironmentVariable = keyof EnvironmentFields;

const requireTogether = (
  value: EnvironmentFields,
  context: z.RefinementCtx,
  names: ReadonlyArray<EnvironmentVariable>,
) => {
  const missing = names.filter((name) => !value[name]);
  const [firstMissing] = missing;

  if (!firstMissing || missing.length === names.length) {
    return;
  }

  const listed = `${names.slice(0, -1).join(", ")} and ${names.at(-1)}`;

  context.addIssue({
    code: "custom",
    message: `${listed} must be configured together.`,
    path: [firstMissing],
  });
};

const validateEnvironment = (
  value: EnvironmentFields,
  context: z.RefinementCtx,
) => {
  const production = value.NODE_ENV === "production";

  requireTogether(value, context, ["GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET"]);
  requireTogether(value, context, ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"]);
  requireTogether(value, context, [
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
  ]);
  requireTogether(value, context, [
    "VALKEY_IAM_CACHE_NAME",
    "VALKEY_IAM_REGION",
    "VALKEY_IAM_USER",
  ]);

  if (production && value.AUTH_TEST_MODE) {
    context.addIssue({
      code: "custom",
      message: "AUTH_TEST_MODE cannot be enabled in production.",
      path: ["AUTH_TEST_MODE"],
    });
  }

  if (production && !value.GITHUB_CLIENT_ID) {
    context.addIssue({
      code: "custom",
      message: "GitHub authentication credentials are required in production.",
      path: ["GITHUB_CLIENT_ID"],
    });
  }

  if (production && !value.GOOGLE_CLIENT_ID) {
    context.addIssue({
      code: "custom",
      message: "Google authentication credentials are required in production.",
      path: ["GOOGLE_CLIENT_ID"],
    });
  }

  if (!value.AUTH_TEST_MODE) {
    const missing = (["AUTH_EMAIL_FROM", "RESEND_API_KEY"] as const).find(
      (name) => !value[name],
    );

    if (missing) {
      context.addIssue({
        code: "custom",
        message:
          "AUTH_EMAIL_FROM and RESEND_API_KEY are required when AUTH_TEST_MODE is disabled.",
        path: [missing],
      });
    }
  }
};

const EnvironmentSchema =
  EnvironmentFieldsSchema.superRefine(validateEnvironment).readonly();

export type Environment = z.infer<typeof EnvironmentSchema>;

export const parseEnvironment = (environment: NodeJS.ProcessEnv): Environment =>
  EnvironmentSchema.parse(environment);
